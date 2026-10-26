# download_data.sh'in Windows PowerShell sürümü (aynı işi yapar).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
docker compose run --rm --entrypoint python freqtrade `
  /freqtrade/user_data/tools/download_binance_archive.py @args
