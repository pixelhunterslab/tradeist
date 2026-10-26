"""
Turnuva için ortak ayarlar ve yardımcılar (Freqtrade'i çağırma, sonuç okuma).

Tüm koşular user_data/tournament/runs/<isim>/ altında, kendi strateji kopyası ve
parametre dosyasıyla çalışır; böylece paralel koşular birbirini bozmaz. Bir koşu
bittiyse ("done" dosyası) tekrar çalıştırılmaz (kesintide kaldığı yerden devam).
"""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pandas as pd

UD = Path("/freqtrade/user_data")
OUT = UD / "tournament"
STRAT_SRC = UD / "strategies"
FT = ["python", str(UD / "tools" / "ft_offline.py")]
CONFIGS = ["--config", str(UD / "config.json"), "--config", str(UD / "config.backtest.json")]

STRATEGIES = ["EmaAdxTrend", "DonchianBreakout", "SupertrendTrend", "RsiBbMeanReversion"]
# Göstergeleri parametreye göre populate_indicators içinde hesaplayan stratejiler
# hyperopt'ta her denemede yeniden hesaplanmalı.
ANALYZE_PER_EPOCH = {"SupertrendTrend", "RsiBbMeanReversion"}

# ---- Dönemler ----
START = "20200301"      # veri 2020-01'de başlıyor; ilk 2 ay göstergelerin ısınması için
IS_END = "20250101"     # in-sample (ayar yapılan) dönem: 2020-03 .. 2024-12
END = "20261026"        # out-of-sample (son sınav): 2025-01 .. bugün
# Walk-forward: 24 ay eğit (hyperopt) -> sonraki 6 ay test et, 6 ayda bir kaydır.
WF_WINDOWS = [
    ("20200301", "20220101", "20220101", "20220701"),
    ("20200701", "20220701", "20220701", "20230101"),
    ("20210101", "20230101", "20230101", "20230701"),
    ("20210701", "20230701", "20230701", "20240101"),
    ("20220101", "20240101", "20240101", "20240701"),
    ("20220701", "20240701", "20240701", "20250101"),
]

# ---- Denenecek varyantlar ----
ATR_MULTIPLIERS = [1.5, 2.0, 2.5, 3.0]
EXIT_MODES = ["trailing", "fixed_tp"]
LEVERAGES = [1, 2, 3, 5]
BASELINE_RISK = {"atr_stop_multiplier": 2.5, "trail_atr_multiplier": 2.5,
                 "exit_mode": "trailing", "leverage": 5}

HYPEROPT_EPOCHS = 50
HYPEROPT_LOSS = "CalmarHyperOptLoss"
RANDOM_STATE = 42


def variant_risk(atr_mult: float, exit_mode: str, leverage: int = 5) -> dict:
    # Takip eden stop mesafesi = ilk stop mesafesi (tek parametre, daha az ayar).
    return {"atr_stop_multiplier": atr_mult, "trail_atr_multiplier": atr_mult,
            "exit_mode": exit_mode, "leverage": leverage}


def variant_name(risk: dict) -> str:
    return f"atr{risk['atr_stop_multiplier']}_{risk['exit_mode']}_lev{risk['leverage']}"


def _prepare(run: str, strategy: str, risk: dict | None, params: Path | None) -> Path:
    d = OUT / "runs" / run
    sdir = d / "strategies"
    sdir.mkdir(parents=True, exist_ok=True)
    (d / "userdir").mkdir(exist_ok=True)
    (d / "bt").mkdir(exist_ok=True)
    for f in ("swing_risk.py", f"{strategy}.py"):
        shutil.copy(STRAT_SRC / f, sdir / f)
    if params:
        shutil.copy(params, sdir / f"{strategy}.json")
    if risk:
        (d / "override.json").write_text(json.dumps({"swing_risk": risk}))
    return d


def _run(d: Path, args: list[str]) -> None:
    cfg = CONFIGS + (["--config", str(d / "override.json")] if (d / "override.json").exists() else [])
    with open(d / "log.txt", "w") as log:
        res = subprocess.run(FT + args[:1] + cfg + args[1:], stdout=log, stderr=subprocess.STDOUT)
    if res.returncode != 0:
        raise RuntimeError(f"Freqtrade hata verdi, bkz. {d / 'log.txt'}")
    (d / "done").touch()


def backtest(run: str, strategy: str, timerange: str, risk: dict | None = None,
             params: Path | None = None) -> Path:
    d = OUT / "runs" / run
    if not (d / "done").exists():
        d = _prepare(run, strategy, risk, params)
        _run(d, ["backtesting", "--strategy", strategy, "--strategy-path", str(d / "strategies"),
                 "--timerange", timerange, "--timeframe-detail", "15m", "--enable-protections",
                 "--export", "trades", "--backtest-directory", str(d / "bt"), "--cache", "none"])
    return next((d / "bt").glob("*.zip"))


def hyperopt(run: str, strategy: str, timerange: str, risk: dict | None = None,
             min_trades: int = 30) -> Path:
    """Sadece verilen (eğitim) döneminde optimize eder; en iyi parametre dosyasını döndürür."""
    d = OUT / "runs" / run
    if not (d / "done").exists():
        d = _prepare(run, strategy, risk, None)
        extra = ["--analyze-per-epoch"] if strategy in ANALYZE_PER_EPOCH else []
        # Freqtrade aynı user_data'da paralel hyperopt'a izin vermez (kilit dosyası);
        # her koşu kendi userdir'ini kullanır, veri ortak klasörden okunur.
        _run(d, ["hyperopt", "--userdir", str(d / "userdir"), "--datadir", str(UD / "data" / "binance"),
                 "--strategy", strategy, "--strategy-path", str(d / "strategies"),
                 "--timerange", timerange, "--spaces", "buy", "sell", "--ignore-missing-spaces",
                 "--hyperopt-loss", HYPEROPT_LOSS, "-e", str(HYPEROPT_EPOCHS), "-j", "1",
                 "--random-state", str(RANDOM_STATE), "--min-trades", str(min_trades),
                 "--enable-protections", *extra])
    params = d / "strategies" / f"{strategy}.json"
    log = (d / "log.txt").read_text()
    if "Quitting now" in log:
        (d / "done").unlink()
        raise RuntimeError(f"Hyperopt çalışmadan çıktı, bkz. {d / 'log.txt'}")
    if not params.exists():
        # Hiçbir deneme min_trades şartını sağlamadı: varsayılan parametreler kullanılır
        # ("defaults_used" ile işaretlenir, raporda görünür).
        params.write_text(json.dumps({"strategy_name": strategy, "params": {},
                                      "defaults_used": True}))
    return params


def load_trades(result_zip: Path) -> pd.DataFrame:
    with zipfile.ZipFile(result_zip) as z:
        name = next(n for n in z.namelist() if n.endswith(".json") and not n.endswith("_config.json"))
        data = json.loads(z.read(name))
    res = next(iter(data["strategy"].values()))
    t = pd.DataFrame(res["trades"])
    if t.empty:
        return t
    for c in ("open_date", "close_date"):
        t[c] = pd.to_datetime(t[c], utc=True)
    return t.sort_values("close_date").reset_index(drop=True)
