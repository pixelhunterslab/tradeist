#!/usr/bin/env sh
# Download all historical futures data needed for backtesting.
# Futures mode automatically also downloads mark-price and funding-rate data.
#   15m = detail timeframe (more realistic stop/trailing fills in backtests)
#   1h, 4h = strategy timeframes, 1d = higher-timeframe trend filter
# Start date 2019-09-01 = launch of Binance USD-M perpetuals; pairs listed
# later simply start at their listing date. Re-running only downloads candles newer than what you have.
set -e
cd "$(dirname "$0")/.."
docker compose run --rm freqtrade download-data \
  --config /freqtrade/user_data/config.json \
  --trading-mode futures \
  --timeframes 15m 1h 4h 1d \
  --timerange 20190901- "$@"
docker compose run --rm freqtrade list-data \
  --config /freqtrade/user_data/config.json \
  --trading-mode futures --show-timerange
