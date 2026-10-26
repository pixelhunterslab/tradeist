#!/usr/bin/env sh
# Backtest için gereken tüm geçmiş vadeli işlem verisini indirir:
# 15m/1h/4h/1d mumlar + mark fiyatı + funding oranları, 2020'den bugüne.
# Kaynak: Binance'in herkese açık arşivi (data.binance.vision); her ülkeden
# erişilebilir. Tekrar çalıştırınca sadece yeni dosyalar indirilir.
set -e
cd "$(dirname "$0")/.."
docker compose run --rm --entrypoint python freqtrade \
  /freqtrade/user_data/tools/download_binance_archive.py "$@"
