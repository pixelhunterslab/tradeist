# Windows PowerShell version of download_data.sh (same behaviour).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
docker compose run --rm freqtrade download-data `
  --config /freqtrade/user_data/config.json `
  --trading-mode futures `
  --timeframes 15m 1h 4h 1d `
  --timerange 20190901- @args
docker compose run --rm freqtrade list-data `
  --config /freqtrade/user_data/config.json `
  --trading-mode futures --show-timerange
