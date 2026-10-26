#!/usr/bin/env sh
# Backtest için gereken tüm geçmiş vadeli işlem verisini indirir.
# Vadeli modda mark fiyatı ve funding oranı verisi de otomatik indirilir.
#   15m = detay zaman dilimi (backtestte daha gerçekçi stop/trailing dolumları)
#   1h, 4h = strateji zaman dilimleri, 1d = üst zaman dilimi trend filtresi
# Başlangıç 2019-09-01 = Binance USD-M perpetual'larının başlangıcı; daha sonra
# listelenen coinler kendi listelenme tarihinden başlar. Tekrar çalıştırınca
# sadece elindekinden yeni mumlar indirilir.
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
