"""
Check which candidate pairs can be traded properly with a small account.

Uses only PUBLIC Binance data (no API key needed). For every pair in the
config's pair_whitelist it compares:

  * Binance's smallest allowed order (min notional / min quantity)
  * the position size our risk rules would actually want to open
    (risk-based size, capped by max margin per trade x leverage)
  * 24h trading volume (liquidity)

Run inside the Freqtrade container:
  docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/check_pairs.py

Options:
  --balance 100          account size in USDT (default: dry_run_wallet)
  --min-volume 100e6     minimum 24h volume in USDT
  --safety 1.2           Freqtrade adds reserves on top of the exchange
                         minimum; we require min_notional * safety
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
    # Simple average of the last `period * 5` true ranges: a stable "typical" ATR.
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

    print(f"Balance {balance:.0f} USDT | leverage {lev:g}x | max notional/trade "
          f"{max_notional:.0f} USDT | risk/trade {risk_usdt:.2f} USDT | stop {mult:g}x ATR\n")
    header = (f"{'pair':16}{'price':>11}{'vol24h(M)':>11}{'minNotional':>12}{'stepValue':>10}"
              f"{'size@1h':>9}{'size@4h':>9}  verdict")
    print(header)
    print("-" * len(header))

    ok_pairs = []
    for pair in cfg["exchange"]["pair_whitelist"]:
        if pair not in ex.markets:
            print(f"{pair:16} not listed on Binance USD-M futures -> EXCLUDE")
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
            reasons.append(f"min order {required:.0f} > planned size")
        elif required > 0.5 * max_notional:
            reasons.append("min order uses >50% of max size (many skips)")
        if step_value > 0.1 * min(sizes):
            reasons.append("quantity step too coarse for exact sizing")
        if vol < args.min_volume / 1e6:
            reasons.append("low volume")
        verdict = "OK" if not reasons else "EXCLUDE: " + "; ".join(reasons)
        if not reasons:
            ok_pairs.append(pair)

        print(f"{pair:16}{price:>11.4g}{vol:>11.0f}{min_notional:>12.2f}{step_value:>10.2f}"
              f"{sizes[0]:>9.0f}{sizes[1]:>9.0f}  {verdict}")

    print("\nsize@1h / size@4h = position size (USDT notional) our risk rules would open "
          "with a typical ATR stop on that timeframe.")
    print("\nSuggested pair_whitelist:")
    print("  " + ",\n  ".join(f'"{p}"' for p in ok_pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
