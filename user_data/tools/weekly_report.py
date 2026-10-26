"""
Haftalık performans özeti -> Telegram.

docker-compose'daki "weekly-report" servisi bunu sürekli çalıştırır. Her
REPORT_WEEKDAY günü (0 = pazartesi) saat REPORT_HOUR'da (REPORT_TZ saat dilimi)
her botun REST API'sinden verileri okur ve tek bir Telegram mesajı gönderir:
haftalık kâr/zarar, kazanma oranı, işlem sayısı, en büyük düşüş, ödenen ücret +
funding ve backtest beklentisiyle karşılaştırma (reports/dryrun_expectations.json).

Container kapalıyken rapor zamanı geçtiyse, açılınca o haftanın raporu gönderilir
(aynı hafta iki kez gönderilmez; durum user_data/logs/weekly_report_state.json'da).

Elle deneme:
  docker compose run --rm --no-deps weekly-report --now          # hemen gönder
  docker compose run --rm --no-deps weekly-report --now --print  # sadece ekrana yaz
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STATE = Path("/freqtrade/user_data/logs/weekly_report_state.json")
EXPECTATIONS = Path("/freqtrade/reports/dryrun_expectations.json")
TZ = ZoneInfo(os.environ.get("REPORT_TZ", "Europe/Istanbul"))
WEEKDAY = int(os.environ.get("REPORT_WEEKDAY", "0"))
HOUR = int(os.environ.get("REPORT_HOUR", "9"))


# ------------------------------------------------------------------ yardımcı
def bots() -> list[tuple[str, str]]:
    raw = os.environ.get("REPORT_BOTS", "Bot=http://freqtrade:8080")
    return [tuple(x.split("=", 1)) for x in raw.split(",") if "=" in x]


def api(url: str, path: str, **params):
    auth = (os.environ.get("FREQTRADE__API_SERVER__USERNAME", ""),
            os.environ.get("FREQTRADE__API_SERVER__PASSWORD", ""))
    r = requests.get(f"{url}/api/v1/{path}", auth=auth, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def closed_trades(url: str) -> list[dict]:
    out, offset = [], 0
    while True:
        page = api(url, "trades", limit=500, offset=offset)
        out += page["trades"]
        offset += len(page["trades"])
        if not page["trades"] or offset >= page.get("total_trades", 0):
            return [t for t in out if not t.get("is_open")]


def ts(t: dict, key: str) -> datetime:
    return datetime.fromtimestamp(t[key] / 1000, tz=timezone.utc)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


def scheduled_time(now: datetime) -> datetime:
    """Bu haftanın rapor zamanı (yerel saat)."""
    local = now.astimezone(TZ)
    day = local.date() - timedelta(days=(local.weekday() - WEEKDAY) % 7)
    return datetime(day.year, day.month, day.day, HOUR, tzinfo=TZ)


# ------------------------------------------------------------------- rapor
def bot_section(label: str, url: str, end: datetime, state: dict, expect: dict) -> str:
    try:
        cfg = api(url, "show_config")
        trades = closed_trades(url)
        open_trades = api(url, "status")
        balance = api(url, "balance")
    except Exception as e:  # noqa: BLE001 - raporda göstermek yeterli
        return f"❌ {label}: bota ulaşılamadı ({type(e).__name__}). Bot çalışıyor mu?"

    # Başlangıç sermayesi = cüzdan toplamı - kapanmış işlemlerin toplam kârı.
    start_cap = float(balance["total"]) - sum(t["profit_abs"] or 0.0 for t in trades)
    started = state["started"][label]
    elapsed_weeks = max((end - datetime.fromisoformat(started)).days / 7, 0.0)
    week_start = end - timedelta(days=7)

    trades.sort(key=lambda t: t["close_timestamp"])
    equity, peak, max_dd = start_cap, start_cap, 0.0
    for t in trades:
        equity += t["profit_abs"] or 0.0
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    current_dd = 1 - equity / peak

    week = [t for t in trades if week_start <= ts(t, "close_timestamp") < end]
    pnl = sum(t["profit_abs"] or 0.0 for t in week)
    eq_week_start = equity - sum(t["profit_abs"] or 0.0 for t in trades
                                 if ts(t, "close_timestamp") >= week_start)
    wins = sum(1 for t in week if (t["profit_abs"] or 0) > 0)
    fees = sum((t.get("fee_open_cost") or 0.0) + (t.get("fee_close_cost") or 0.0) for t in week)
    funding = sum(t.get("funding_fees") or 0.0 for t in week)
    unrealized = sum(t.get("total_profit_abs", t.get("profit_abs")) or 0.0 for t in open_trades)

    mode = "SANAL (dry-run)" if cfg.get("dry_run") else "GERÇEK PARA"
    lines = [f"📊 {label} — {cfg.get('strategy')} [{mode}]",
             f"Bu hafta: {len(week)} işlem kapandı, kâr/zarar {pnl:+.2f} USDT "
             f"({100 * pnl / eq_week_start if eq_week_start else 0:+.2f}%)",
             f"Kazanma oranı (hafta): {100 * wins / len(week):.0f}%" if week
             else "Kazanma oranı (hafta): - (kapanan işlem yok)",
             f"Ödenen ücret: {fees:.2f} USDT, funding: {funding:+.2f} USDT (+ = alındı)",
             f"Açık işlem: {len(open_trades)} (anlık {unrealized:+.2f} USDT)",
             f"Toplam: {len(trades)} işlem, bakiye {equity:.2f} USDT "
             f"({100 * (equity / start_cap - 1):+.1f}% başlangıçtan beri)",
             f"En büyük düşüş: {100 * max_dd:.1f}% (şu an zirveden {100 * current_dd:.1f}% aşağıda)"]

    e = expect.get(cfg.get("strategy"))
    if e:
        exp_trades = e["trades_per_week"] * elapsed_weeks
        exp_ret = ((1 + e["weekly_return_pct"] / 100) ** elapsed_weeks - 1) * 100
        win_all = (f"{100 * sum(1 for t in trades if (t['profit_abs'] or 0) > 0) / len(trades):.0f}%"
                   if trades else "-")
        lines += [f"Backtest beklentisi ({elapsed_weeks:.1f} hafta için):",
                  f"  işlem ~{exp_trades:.1f} (gerçek {len(trades)}), getiri ~{exp_ret:+.1f}% "
                  f"(gerçek {100 * (equity / start_cap - 1):+.1f}%)",
                  f"  kazanma oranı ~{e['win_rate_pct']:.0f}% (gerçek {win_all}), "
                  f"backtestteki en kötü düşüş {e['max_dd_pct']:.0f}%"]
        if 100 * max_dd > e["max_dd_pct"]:
            lines.append("⚠️ Düşüş, backtestteki en kötü düşüşten BÜYÜK. Gözden geçir.")
        if exp_trades >= 4 and not trades:
            lines.append("⚠️ Beklenen işlemler hiç gelmedi. Bot gerçekten işlem arıyor mu?")
    return "\n".join(lines)


def build_report(end: datetime, state: dict) -> str:
    try:
        expect = json.loads(EXPECTATIONS.read_text())
    except (OSError, ValueError):
        expect = {}
    header = (f"🗓 Haftalık özet — {(end - timedelta(days=7)).astimezone(TZ):%d.%m} – "
              f"{end.astimezone(TZ):%d.%m.%Y}")
    note = ("Not: işlem sayısı az olduğu için tek haftalık sonuçlar istatistiksel olarak "
            "anlamsızdır; eğilime bakın.")
    return "\n\n".join([header, *(bot_section(l, u, end, state, expect) for l, u in bots()), note])


def send_telegram(text: str) -> None:
    token = os.environ.get("FREQTRADE__TELEGRAM__TOKEN", "")
    chat = os.environ.get("FREQTRADE__TELEGRAM__CHAT_ID", "")
    if not token or not chat:
        raise RuntimeError("Telegram token/chat id .env'de yok")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text}, timeout=30)
    r.raise_for_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="hemen bir rapor gönder ve çık")
    ap.add_argument("--print", action="store_true", help="Telegram yerine ekrana yaz")
    args = ap.parse_args()
    telegram_on = os.environ.get("FREQTRADE__TELEGRAM__ENABLED", "").lower() == "true"
    if not args.print and not telegram_on:
        print("Telegram kapalı (.env: FREQTRADE__TELEGRAM__ENABLED); rapor sadece log'a yazılır.",
              flush=True)
    deliver = send_telegram if telegram_on and not args.print else print
    # Beklentiyle karşılaştırma için dry-run'ın başlangıcı = servisin ilk çalıştığı an.
    state = load_state()
    for label, _ in bots():
        state.setdefault("started", {}).setdefault(label, datetime.now(timezone.utc).isoformat())
    save_state(state)

    if args.now:
        deliver(build_report(datetime.now(timezone.utc), state))
        save_state(state)
        return 0

    print(f"Haftalık rapor servisi çalışıyor: her {WEEKDAY}. gün saat {HOUR}:00 ({TZ}).",
          flush=True)
    while True:
        state = load_state()
        now = datetime.now(timezone.utc)
        due = scheduled_time(now)
        last = state.get("last_sent")
        if now >= due and (not last or datetime.fromisoformat(last) < due):
            try:
                deliver(build_report(due, state))
                state["last_sent"] = due.isoformat()
                save_state(state)
                print(f"Rapor gönderildi: {due}", flush=True)
            except Exception as e:  # noqa: BLE001 - tekrar denenecek
                print(f"Rapor gönderilemedi, 10 dk sonra tekrar: {e}", flush=True)
                time.sleep(600)
                continue
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
