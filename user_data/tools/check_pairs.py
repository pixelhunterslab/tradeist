"""
Hangi aday coinlerin küçük bir hesapla düzgün işlem görebileceğini kontrol eder.

Sadece HERKESE AÇIK Binance verisi kullanır (API anahtarı gerekmez). Config'deki
pair_whitelist'teki her coin için şunları karşılaştırır:

  * Binance'in izin verdiği en küçük emir (min notional / min miktar)
  * risk kurallarımızın gerçekten açmak isteyeceği pozisyon büyüklüğü
    (riske göre büyüklük, işlem başına max marjin x kaldıraç ile sınırlı)
  * 24 saatlik işlem hacmi (likidite)

Freqtrade konteyneri içinde çalıştır:
  docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/check_pairs.py

Seçenekler:
  --balance 100          hesap büyüklüğü, USDT (varsayılan: dry_run_wallet)
  --min-volume 100e6     en az 24s hacim, USDT
  --safety 1.2           Freqtrade borsanın minimumunun üstüne pay ekler;
                         biz min_notional * safety şartını arıyoruz
"""
import argparse
import sys

import ccxt
from freqtrade.configuration.load_config import load_config_file

CONFIG = "/freqtrade/user_data/config.json"


def atr_pct(exchange, symbol, timeframe, period):
    candles = exchange.fetch_ohlcv(symbol, timeframe, limit=period * 10)
    trs = []
    for prev, cur in zip(candles, candles[1:]):
        high, low, prev_close = cur[2], cur[3], prev[4]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)) / cur[4])
    # Son `period * 5` true range'in basit ortalaması: istikrarlı, "tipik" bir ATR.
    recent = trs[-period * 5:]
    return sum(recent) / len(recent)


def main():
    cfg = load_config_file(CONFIG)
    risk = cfg["swing_risk"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--balance", type=float, default=float(cfg.get("dry_run_wallet", 100)))
    ap.add_argument("--min-volume", type=float, default=100e6)
    ap.add_argument("--safety", type=float, default=1.2)
    args = ap.parse_args()

    balance = args.balance
    lev = min(float(risk["leverage"]), float(risk["max_leverage"]))
    max_notional = balance * risk["max_margin_per_trade_pct_of_balance"] / 100 * lev
    risk_usdt = balance * risk["max_loss_per_trade_pct_of_balance"] / 100
    mult = float(risk["atr_stop_multiplier"])

    ex = ccxt.binanceusdm({"enableRateLimit": True})
    ex.load_markets()
    tickers = ex.fetch_tickers()

    print(f"Bakiye {balance:.0f} USDT | kaldıraç {lev:g}x | işlem başına max pozisyon "
          f"{max_notional:.0f} USDT | işlem başına risk {risk_usdt:.2f} USDT | stop {mult:g}x ATR\n")
    header = (f"{'coin':16}{'fiyat':>11}{'hacim24s(M)':>12}{'minEmir':>10}{'adımDeğeri':>11}"
              f"{'boyut@1s':>9}{'boyut@4s':>9}  karar")
    print(header)
    print("-" * len(header))

    ok_pairs = []
    for pair in cfg["exchange"]["pair_whitelist"]:
        if pair not in ex.markets:
            print(f"{pair:16} Binance USD-M vadelide listelenmiyor -> ÇIKAR")
            continue
        m = ex.markets[pair]
        price = tickers[pair]["last"]
        vol = (tickers[pair].get("quoteVolume") or 0) / 1e6
        min_cost = m["limits"]["cost"]["min"] or 0
        min_amt = m["limits"]["amount"]["min"] or 0
        step = m["precision"]["amount"] or min_amt
        min_notional = max(min_cost, min_amt * price)
        step_value = step * price

        sizes = []
        for tf in ("1h", "4h"):
            stop_dist = mult * atr_pct(ex, pair, tf, int(risk["atr_period"]))
            sizes.append(min(risk_usdt / stop_dist, max_notional))

        reasons = []
        required = min_notional * args.safety
        if required > min(sizes):
            reasons.append(f"min emir {required:.0f} > planlanan büyüklük")
        elif required > 0.5 * max_notional:
            reasons.append("min emir, max büyüklüğün %50'sinden fazla (çok işlem atlanır)")
        if step_value > 0.1 * min(sizes):
            reasons.append("miktar adımı hassas boyutlama için çok kaba")
        if vol < args.min_volume / 1e6:
            reasons.append("düşük hacim")
        verdict = "UYGUN" if not reasons else "ÇIKAR: " + "; ".join(reasons)
        if not reasons:
            ok_pairs.append(pair)

        print(f"{pair:16}{price:>11.4g}{vol:>12.0f}{min_notional:>10.2f}{step_value:>11.2f}"
              f"{sizes[0]:>9.0f}{sizes[1]:>9.0f}  {verdict}")

    print("\nboyut@1s / boyut@4s = o zaman diliminde tipik bir ATR stopuyla risk kurallarımızın "
          "açacağı pozisyon büyüklüğü (USDT).")
    print("\nÖnerilen pair_whitelist:")
    print("  " + ",\n  ".join(f'"{p}"' for p in ok_pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
