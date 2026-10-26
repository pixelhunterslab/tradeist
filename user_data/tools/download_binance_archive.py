"""
Binance'in herkese açık veri arşivinden (data.binance.vision) geçmiş vadeli
işlem verisini indirir ve Freqtrade'in kendi formatında kaydeder.

Freqtrade'in normal "download-data" komutu Binance'in canlı API'sini
(fapi.binance.com) kullanır. Bu API bazı ülkelerden/sunuculardan erişilemez
(HTTP 451). Arşiv ise her yerden erişilebilir ve aynı veriyi içerir.

İndirilenler (config'deki her coin için):
  * vadeli mumlar: 15m, 1h, 4h, 1d          -> <PAIR>-<tf>-futures.feather
  * mark fiyatı mumları: 1h                 -> <PAIR>-1h-mark.feather
  * funding oranları (sadece aylık arşiv)   -> <PAIR>-1h-funding_rate.feather

Arşiv zip'leri user_data/data/_archive_cache/ içinde saklanır; tekrar
çalıştırınca sadece eksik/yeni dosyalar indirilir.

Çalıştırma:
  docker compose run --rm --entrypoint python freqtrade \
      /freqtrade/user_data/tools/download_binance_archive.py
"""
import argparse
import io
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from freqtrade.configuration.load_config import load_config_file
from freqtrade.data.history import get_datahandler
from freqtrade.enums import CandleType

CONFIG = "/freqtrade/user_data/config.json"
BASE = "https://data.binance.vision/data/futures/um"
FIRST_MONTH = date(2019, 9, 1)
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
MARK_TF = "1h"
OHLCV = ["date", "open", "high", "low", "close", "volume"]

session = requests.Session()


def months(until: date):
    d = FIRST_MONTH
    while d < until:
        yield d
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def fetch(url: str, cache: Path, refresh: bool) -> bytes | None:
    """Zip dosyasını indir (önbellekte varsa oradan oku). Arşivde yoksa None."""
    if cache.exists() and not refresh:
        return cache.read_bytes()
    cache.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            r = session.get(url, timeout=60)
        except requests.RequestException:
            continue
        if r.status_code == 404:
            return None
        if r.ok:
            cache.write_bytes(r.content)
            return r.content
    raise RuntimeError(f"İndirilemedi: {url}")


def read_csv(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0])
    first = text[:1]
    header = 0 if not first.isdigit() else None  # eski dosyalarda başlık satırı yok
    return pd.read_csv(io.BytesIO(text), header=header)


def to_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.iloc[:, :6].copy()
    df.columns = OHLCV
    ts = df["date"].astype("int64")
    ts = ts.where(ts < 10**14, ts // 1000)  # mikro saniye -> milisaniye
    df["date"] = pd.to_datetime(ts, unit="ms", utc=True)
    return df.astype({c: "float64" for c in OHLCV[1:]})


def to_funding(df: pd.DataFrame) -> pd.DataFrame:
    # sütunlar: calc_time, funding_interval_hours, last_funding_rate
    date_ = pd.to_datetime(df.iloc[:, 0].astype("int64"), unit="ms", utc=True).dt.floor("h")
    return pd.DataFrame({"date": date_, "funding_rate": df.iloc[:, -1].astype("float64")})


def collect(kind: str, symbol: str, tf: str | None, cache_dir: Path, today: date, workers: int):
    """Bir veri türü için tüm aylık + (bu ayın) günlük dosyaları topla."""
    this_month = today.replace(day=1)
    sub = f"{kind}/{symbol}/{tf}" if tf else f"{kind}/{symbol}"
    name = f"{symbol}-{tf}" if tf else f"{symbol}-{kind}"
    jobs = [(f"{BASE}/monthly/{sub}/{name}-{m:%Y-%m}.zip",
             cache_dir / "monthly" / sub / f"{m:%Y-%m}.zip", False)
            for m in months(this_month)]
    if kind != "fundingRate":  # funding için günlük arşiv yok
        d = this_month
        while d < today:
            # günlük dosyalar ay bitince aylık dosyayla değiştirilebilir; her zaman tazele
            jobs.append((f"{BASE}/daily/{sub}/{name}-{d:%Y-%m-%d}.zip",
                         cache_dir / "daily" / sub / f"{d:%Y-%m-%d}.zip", True))
            d += timedelta(days=1)
    with ThreadPoolExecutor(workers) as ex:
        raws = list(ex.map(lambda j: fetch(*j), jobs))
    frames = [read_csv(r) for r in raws if r]
    return frames


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="*", help="varsayılan: config'deki pair_whitelist")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    cfg = load_config_file(CONFIG)
    pairs = args.pairs or cfg["exchange"]["pair_whitelist"]
    datadir = Path("/freqtrade/user_data/data/binance")
    cache_dir = Path("/freqtrade/user_data/data/_archive_cache")
    handler = get_datahandler(datadir, cfg.get("dataformat_ohlcv", "feather"))
    today = date.today()

    for pair in pairs:
        symbol = pair.split("/")[0] + pair.split("/")[1].split(":")[0]
        for tf in TIMEFRAMES:
            frames = collect("klines", symbol, tf, cache_dir, today, args.workers)
            store(handler, pair, tf, CandleType.FUTURES, [to_ohlcv(f) for f in frames])
        frames = collect("markPriceKlines", symbol, MARK_TF, cache_dir, today, args.workers)
        store(handler, pair, MARK_TF, CandleType.MARK, [to_ohlcv(f) for f in frames])
        frames = collect("fundingRate", symbol, None, cache_dir, today, args.workers)
        store(handler, pair, "1h", CandleType.FUNDING_RATE, [to_funding(f) for f in frames])
    return 0


def store(handler, pair, tf, candle_type, frames):
    if not frames:
        print(f"{pair:16} {tf:>4} {candle_type.value:13} arşivde veri yok")
        return
    df = (pd.concat(frames).drop_duplicates("date", keep="last")
          .sort_values("date").reset_index(drop=True))
    handler.ohlcv_store(pair, tf, df, candle_type)
    print(f"{pair:16} {tf:>4} {candle_type.value:13} {len(df):>7} satır  "
          f"{df['date'].iloc[0]:%Y-%m-%d} -> {df['date'].iloc[-1]:%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    sys.exit(main())
