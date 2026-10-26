"""
Turnuva sonuçlarından reports/strategy_tournament.md ve grafikleri üretir.

  docker compose --profile research run --rm research \
      /freqtrade/user_data/tools/tournament/report.py

Elle yazılan sonuç/yorum bölümü reports/tournament_conclusion.md dosyasından
alınır ve raporun başına eklenir (rakamlar bu script tarafından hesaplanır).
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402
import metrics as m  # noqa: E402
from freqtrade.data.history import load_pair_history  # noqa: E402
from freqtrade.enums import CandleType  # noqa: E402

REPORTS = Path("/freqtrade/reports")
IMG = REPORTS / "img"
DATADIR = c.UD / "data" / "binance"
# Sabit renk sırası (her strateji her grafikte aynı renk).
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
TR_MONTHS = "Oca Şub Mar Nis May Haz Tem Ağu Eyl Eki Kas Ara".split()


# ----------------------------------------------------------------- yardımcı
def fmt(x, d=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    if isinstance(x, float) and np.isinf(x):
        return "∞"
    return f"{x:.{d}f}"


def table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def load_results() -> list[dict]:
    files = sorted((c.OUT / "results").glob("*.json"))
    order = {s: i for i, s in enumerate(c.STRATEGIES + ["ComboStrategy"])}
    res = [json.loads(f.read_text()) for f in files]
    return sorted(res, key=lambda r: order.get(r["strategy"], 99))


def equity(zip_path, start, end):
    t = c.load_trades(Path(zip_path))
    return t, m.equity_curve(t, start, end)


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


# ------------------------------------------------------------------ grafikler
def plot_equity(results, colors) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=False,
                             gridspec_kw={"width_ratios": [2.6, 1]})
    for ax, (key, start, end, title) in zip(axes, [
            ("zip_is", c.START, c.IS_END, "In-sample 2020-03 → 2024-12 (ayar dönemi)"),
            ("zip_oos", c.IS_END, c.END, "Out-of-sample 2025-01 → 2026-10 (son sınav)")]):
        for r in results:
            _, eq = equity(r[key], start, end)
            ax.plot(eq.index, eq.values, color=colors[r["strategy"]], linewidth=1.8,
                    label=r["strategy"])
            ax.annotate(f"{eq.iloc[-1]:.0f}", (eq.index[-1], eq.iloc[-1]), fontsize=8,
                        color=INK2, xytext=(4, 0), textcoords="offset points", va="center")
        ax.axhline(100, color=INK2, linewidth=0.8, linestyle="--")
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_ylabel("Bakiye (USDT, 100 ile başlar)", fontsize=8, color=INK2)
        style(ax)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    path = IMG / "equity_curves.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path.name


def plot_leverage(res, color) -> str:
    sweep = res["leverage_sweep"]
    levs = sorted(sweep, key=int)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, per, title in zip(axes, ("is", "oos"), ("In-sample", "Out-of-sample")):
        x = [sweep[lv][per]["max_dd_pct"] for lv in levs]
        y = [sweep[lv][per]["cagr_pct"] for lv in levs]
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=7)
        for lv, xi, yi in zip(levs, x, y):
            ax.annotate(f"{lv}x", (xi, yi), fontsize=9, color=INK, xytext=(6, 4),
                        textcoords="offset points")
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_xlabel("En büyük düşüş (%)", fontsize=8, color=INK2)
        ax.set_ylabel("Yıllık getiri (%)", fontsize=8, color=INK2)
        ax.set_title(f"{res['strategy']} – {title}", fontsize=10, color=INK, loc="left")
        style(ax)
    fig.tight_layout()
    path = IMG / f"leverage_{res['strategy']}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path.name


# ---------------------------------------------------------------- analizler
def btc_regimes() -> pd.Series:
    """Her ay: BTC aylık getirisi > +%10 yükseliş, < -%10 düşüş, arası yatay."""
    df = load_pair_history(pair="BTC/USDT:USDT", timeframe="1d", datadir=DATADIR,
                           candle_type=CandleType.FUTURES)
    close = df.set_index("date")["close"].resample("ME").last()
    ret = close.pct_change()
    reg = pd.Series("yatay", index=ret.index)
    reg[ret > 0.10] = "yükseliş"
    reg[ret < -0.10] = "düşüş"
    return reg.iloc[1:]


def monthly_returns(r) -> pd.Series:
    parts = []
    for key, start, end in (("zip_is", c.START, c.IS_END), ("zip_oos", c.IS_END, c.END)):
        _, eq = equity(r[key], start, end)
        me = eq.resample("ME").last()
        prev = me.shift(1)
        prev.iloc[0] = m.START_BALANCE
        parts.append(me / prev - 1)
    return pd.concat(parts)


def regime_table(results, regimes) -> str:
    rows = []
    for r in results:
        mr = monthly_returns(r)
        joined = pd.DataFrame({"ret": mr, "reg": regimes.reindex(mr.index)}).dropna()
        row = [r["strategy"]]
        for reg in ("yükseliş", "düşüş", "yatay"):
            x = joined[joined.reg == reg].ret
            row.append(f"{100 * x.mean():+.1f}% ({100 * (x > 0).mean():.0f}% ay kârlı)"
                       if len(x) else "-")
        rows.append(row)
    counts = regimes[(regimes.index >= pd.Timestamp(c.START, tz="UTC"))].value_counts()
    head = [f"Strateji", f"Yükseliş ayları ({counts.get('yükseliş', 0)})",
            f"Düşüş ayları ({counts.get('düşüş', 0)})", f"Yatay aylar ({counts.get('yatay', 0)})"]
    return table(head, rows)


def losing_streak(t: pd.DataFrame) -> int:
    best = cur = 0
    for p in t.sort_values("close_date")["profit_abs"]:
        cur = cur + 1 if p < 0 else 0
        best = max(best, cur)
    return best


def underwater(eq: pd.Series) -> tuple[int, bool, pd.Timestamp, float]:
    """En uzun 'zirveden aşağıda' kalma süresi (gün), toparlandı mı, en kötü düşüş tarihi."""
    peak = eq.cummax()
    under = eq < peak
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    dd = 1 - eq / peak
    return longest, not under.iloc[-1], dd.idxmax(), float(dd.max())


def noise_stops(t: pd.DataFrame, hours: int = 48) -> tuple[int, int]:
    """Stop olduktan sonra 48 saat içinde fiyat giriş fiyatına geri döndüyse 'gürültü stopu'."""
    stops = t[t.exit_reason == "stop_loss"]
    noisy = 0
    cache = {}
    for tr in stops.itertuples():
        if tr.pair not in cache:
            cache[tr.pair] = load_pair_history(pair=tr.pair, timeframe="1h", datadir=DATADIR,
                                               candle_type=CandleType.FUTURES)
        df = cache[tr.pair]
        after = df[(df.date > tr.close_date) & (df.date <= tr.close_date + pd.Timedelta(hours=hours))]
        if len(after) and ((not tr.is_short and after.high.max() >= tr.open_rate)
                           or (tr.is_short and after.low.min() <= tr.open_rate)):
            noisy += 1
    return noisy, len(stops)


def deep_dive(r) -> str:
    lines = []
    for key, start, end, label in (("zip_is", c.START, c.IS_END, "In-sample (2020-03 → 2024-12)"),
                                   ("zip_oos", c.IS_END, c.END, "Out-of-sample (2025-01 → 2026-10)")):
        t, eq = equity(r[key], start, end)
        if t.empty:
            lines.append(f"**{label}:** işlem yok.\n")
            continue
        longest, recovered, dd_date, dd = underwater(eq)
        noisy, n_stops = noise_stops(t)
        side = t.groupby("is_short")["profit_abs"].agg(["count", "sum"])
        pairs = t.groupby("pair")["profit_abs"].agg(["count", "sum"]).sort_values("sum")
        exits = t.groupby("exit_reason")["profit_abs"].agg(["count", "sum"])
        lines.append(f"**{label}**\n")
        lines.append(f"- En uzun kayıp serisi: **{losing_streak(t)} işlem üst üste zarar**")
        lines.append(f"- En büyük düşüş: **%{100 * dd:.1f}** (dip: {dd_date:%Y-%m-%d})")
        lines.append(f"- Zirveden aşağıda kalınan en uzun süre: **{longest} gün**"
                     + ("" if recovered else " (dönem sonunda hâlâ zirvenin altında)"))
        lines.append(f"- Gürültü stopları: {n_stops} stoptan **{noisy}** tanesinde (%"
                     f"{100 * noisy / max(n_stops, 1):.0f}) fiyat 48 saat içinde giriş fiyatına geri döndü")
        lines.append("- Long / short: " + ", ".join(
            f"{'short' if s else 'long'} {int(v['count'])} işlem, {v['sum']:+.1f} USDT"
            for s, v in side.iterrows()))
        lines.append("- Coinler (en kötüden iyiye): " + ", ".join(
            f"{p.split('/')[0]} {v['sum']:+.1f}" for p, v in pairs.iterrows()))
        lines.append("- Çıkış sebepleri: " + ", ".join(
            f"{k} {int(v['count'])} ({v['sum']:+.1f} USDT)" for k, v in exits.iterrows()))
        worst = t.nsmallest(1, "profit_abs").iloc[0]
        lines.append(f"- En kötü tek işlem: {worst.pair.split('/')[0]} "
                     f"{'short' if worst.is_short else 'long'} {worst.open_date:%Y-%m-%d}, "
                     f"{worst.profit_abs:+.2f} USDT\n")
    return "\n".join(lines)


# ----------------------------------------------------------------------- rapor
def main():
    IMG.mkdir(parents=True, exist_ok=True)
    results = load_results()
    colors = {r["strategy"]: COLORS[i % len(COLORS)] for i, r in enumerate(results)}
    ranked = sorted(results, key=lambda r: r["robustness"]["score"], reverse=True)
    md = ["# Strateji Turnuvası (Aşama 3)\n",
          f"_Otomatik üretildi: `user_data/tools/tournament/report.py`. Veri: Binance USDⓈ-M, "
          f"ETH, SOL, XRP, BNB, DOGE, ADA._\n"]

    concl = REPORTS / "tournament_conclusion.md"
    if concl.exists():
        md.append(concl.read_text())

    md.append("## 1. Karşılaştırma tablosu\n")
    md.append("Sıralama **sağlamlık puanına** göre (toplam kâra göre değil). In-sample ve "
              "out-of-sample ayrı koşulardır, ikisi de 100 USDT ile başlar.\n")
    rows = []
    for r in ranked:
        i, o, rb = r["is"], r["oos"], r["robustness"]
        rows.append([f"**{r['strategy']}**", r["chosen_variant"].replace("_lev5", ""),
                     i["trades"], fmt(i["return_pct"], 0) + "%", fmt(i["max_dd_pct"], 0) + "%",
                     fmt(i["profit_factor"], 2),
                     o["trades"], fmt(o["return_pct"], 0) + "%", fmt(o["max_dd_pct"], 0) + "%",
                     fmt(o["calmar"], 2), fmt(o["profit_factor"], 2),
                     f"{rb['wf_profitable']}/{len(r['walk_forward'])}", fmt(rb["score"], 2),
                     "✅" if rb["passed"] else "❌"])
    md.append(table(["Strateji", "Varyant", "IS işlem", "IS getiri", "IS max düşüş", "IS kâr fakt.",
                     "OOS işlem", "OOS getiri", "OOS max düşüş", "OOS Calmar", "OOS kâr fakt.",
                     "WF kârlı pencere", "Puan", "Geçti"], rows))
    md.append("\n**Eleme sebepleri:**\n")
    for r in ranked:
        rs = r["robustness"]["reject_reasons"]
        md.append(f"- **{r['strategy']}**: " + ("hiçbiri, tüm şartları geçti" if not rs else "; ".join(rs)))
    md.append("")

    md.append("## 2. Bakiye eğrileri\n")
    md.append(f"![Bakiye eğrileri](img/{plot_equity(results, colors)})\n")
    md.append("Sağdaki son sınav (out-of-sample) dönemi, stratejilerin ayar yapılırken hiç görmediği "
              "veridir. Eğriler sadece kapanmış işlemleri içerir.\n")

    md.append("## 3. Walk-forward (24 ay ayarla → sonraki 6 ayda test et)\n")
    windows = [w["window"] for w in results[0]["walk_forward"]]
    rows = []
    for r in results:
        rows.append([r["strategy"]] + [f"{w['return_pct']:+.0f}% ({w['trades']})"
                                       for w in r["walk_forward"]])
    md.append(table(["Strateji"] + [f"{w[:4]}-{w[4:6]}→{w[9:13]}-{w[13:15]}" for w in windows], rows))
    md.append("\nHer hücre: o 6 aylık test penceresinin getirisi (işlem sayısı). Her pencere "
              "100 USDT ile başlar ve parametreler sadece önceki 24 ayda ayarlanmıştır.\n")

    md.append("## 4. Piyasa dönemlerine göre (yükseliş / düşüş / yatay)\n")
    md.append("Ay sınıflandırması BTC'nin aylık getirisine göre: > +%10 yükseliş, < -%10 düşüş, "
              "arası yatay. Hücre: o tür aylarda stratejinin ortalama aylık getirisi.\n")
    md.append(regime_table(results, btc_regimes()) + "\n")

    md.append("## 5. ATR stop çarpanı ve çıkış modu (sadece in-sample)\n")
    md.append("Varyant seçimi **sadece in-sample** puanıyla yapıldı (out-of-sample'a bakılmadan).\n")
    for r in results:
        rows = []
        for name, g in sorted(r["grid"].items()):
            i = g["is"]
            rows.append([("**→ " if name == r["chosen_variant"] else "") + name.replace("_lev5", "")
                         + ("**" if name == r["chosen_variant"] else ""),
                         i["trades"], fmt(i["return_pct"], 0) + "%", fmt(i["max_dd_pct"], 0) + "%",
                         fmt(i["calmar"], 2), fmt(i["profit_factor"], 2), fmt(g["is_score"], 2)])
        md.append(f"**{r['strategy']}**\n")
        md.append(table(["Varyant", "İşlem", "Getiri", "Max düşüş", "Calmar", "Kâr fakt.",
                         "IS puanı"], rows) + "\n")
    trail = [g["is_score"] for r in results for n, g in r["grid"].items() if "trailing" in n]
    tp = [g["is_score"] for r in results for n, g in r["grid"].items() if "fixed_tp" in n]
    md.append(f"Ortalama IS puanı: takip eden stop **{np.mean(trail):.2f}**, sabit kâr al "
              f"**{np.mean(tp):.2f}**.\n")

    finalists = [r for r in ranked if "leverage_sweep" in r]
    if finalists:
        md.append("## 6. Kaldıraç taraması (en yüksek puanlı 2 strateji)\n")
        md.append("Risk kuralları aynı (işlem başına en fazla %5 kayıp, en fazla %25 marjin). "
                  "Düşük kaldıraçta aynı marjinle daha küçük pozisyon açılabildiği için risk de "
                  "küçülür.\n")
        for r in finalists:
            sw = r["leverage_sweep"]
            rows = [[f"{lv}x", sw[lv]["is"]["trades"], fmt(sw[lv]["is"]["return_pct"], 0) + "%",
                     fmt(sw[lv]["is"]["max_dd_pct"], 0) + "%", fmt(sw[lv]["is"]["calmar"], 2),
                     sw[lv]["oos"]["trades"], fmt(sw[lv]["oos"]["return_pct"], 0) + "%",
                     fmt(sw[lv]["oos"]["max_dd_pct"], 0) + "%", fmt(sw[lv]["oos"]["calmar"], 2)]
                    for lv in sorted(sw, key=int)]
            md.append(f"**{r['strategy']}**\n")
            md.append(table(["Kaldıraç", "IS işlem", "IS getiri", "IS max düşüş", "IS Calmar",
                             "OOS işlem", "OOS getiri", "OOS max düşüş", "OOS Calmar"], rows))
            md.append(f"\n![Kaldıraç](img/{plot_leverage(r, colors[r['strategy']])})\n")

    md.append("## 7. Ayrıntılı inceleme: zayıf yanlar\n")
    for r in ranked[:2]:
        md.append(f"### {r['strategy']} ({r['chosen_variant'].replace('_lev5', '')})\n")
        if r.get("defaults_used"):
            md.append("⚠️ In-sample hyperopt'ta hiçbir deneme minimum işlem sayısını sağlamadı; "
                      "varsayılan parametreler kullanıldı.\n")
        md.append(f"Parametreler (in-sample hyperopt): `{json.dumps(r['params_is'].get('buy', {}) | r['params_is'].get('sell', {}))}`\n")
        md.append(deep_dive(r))

    md.append("## 8. Yöntem\n")
    md.append(f"""- **Dönemler:** in-sample {c.START[:4]}-{c.START[4:6]} → 2024-12 (ayar ve seçim), out-of-sample 2025-01 → {c.END[:4]}-{c.END[4:6]}-{c.END[6:]} (son sınav, ayarda hiç kullanılmadı).
- **Maliyet:** her alış ve satışta %0.1 (%0.05 Binance taker ücreti + %0.05 kayma payı). Funding ücretleri gerçek funding oranı geçmişinden hesaplandı.
- **Gerçekçilik:** 15 dakikalık detay mumlarla stop/takip eden stop dolumları simüle edildi; korumalar (cooldown, stoploss guard, max drawdown, low profit pairs) açık; en fazla 3 açık işlem; 100 USDT başlangıç.
- **Hyperopt:** sadece eğitim döneminde, strateji başına 2-3 parametre, {c.HYPEROPT_EPOCHS} deneme, kayıp fonksiyonu {c.HYPEROPT_LOSS}, sabit rastgele tohum ({c.RANDOM_STATE}).
- **Varyantlar:** ATR stop çarpanı {c.ATR_MULTIPLIERS} × çıkış modu (takip eden stop / sabit kâr al = 2R). Seçim sadece in-sample puanıyla.
- **Walk-forward:** 6 pencere; her birinde önceki 24 ayda ayar, sonraki 6 ayda test.
- **Eleme kuralları (sonuçlardan önce sabitlendi):** IS ≥ {m.MIN_IS_TRADES} işlem, OOS ≥ {m.MIN_OOS_TRADES} işlem, OOS kârlı ve kâr faktörü ≥ {m.MIN_OOS_PROFIT_FACTOR}, IS ve OOS max düşüş ≤ %{m.MAX_DRAWDOWN * 100:.0f}, walk-forward'da en az {m.MIN_WF_PROFITABLE}/6 kârlı pencere.
- **Puan (0-1):** %30 OOS Calmar, %20 OOS kâr faktörü, %20 walk-forward tutarlılığı, %15 max düşüş, %15 OOS/IS getiri oranı (bozulma).
- **Sınırlar:** Binance arşivinde SOL/XRP için 2022'de ~5 günlük veri boşluğu var; bakiye eğrisi açık işlemlerin anlık zararını içermez; geçmiş performans geleceği garanti etmez.
""")
    (REPORTS / "strategy_tournament.md").write_text("\n".join(md))
    summary = [{k: r[k] for k in ("strategy", "chosen_variant", "risk", "params_is", "is", "oos",
                                  "robustness", "walk_forward")} for r in ranked]
    (REPORTS / "tournament_results.json").write_text(json.dumps(summary, indent=1, default=str))
    print("Rapor yazıldı:", REPORTS / "strategy_tournament.md")


if __name__ == "__main__":
    main()
