"""
Strateji 3 - Supertrend trend takibi.

Mantık:
  * Supertrend (ATR tabanlı bir trend çizgisi) yön değiştirip yukarı dönerse
    -> LONG, aşağı dönerse -> SHORT.
  * Çıkış: Supertrend ters yöne dönünce (veya ortak ATR stop / takip eden stop).
Parametreler: st_period, st_multiplier (2 adet).
"""
import sys
from pathlib import Path

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy

sys.path.append(str(Path(__file__).parent))
from swing_risk import SwingRiskMixin  # noqa: E402


def supertrend(dataframe: DataFrame, period: int, multiplier: float) -> np.ndarray:
    """Yön dizisi döndürür: +1 yukarı trend, -1 aşağı trend (0 = henüz yok)."""
    high, low, close = (dataframe[c].to_numpy() for c in ("high", "low", "close"))
    atr = ta.ATR(dataframe, timeperiod=period).to_numpy()
    mid = (high + low) / 2
    upper_basic, lower_basic = mid + multiplier * atr, mid - multiplier * atr
    upper, lower = upper_basic.copy(), lower_basic.copy()
    direction = np.zeros(len(close))
    for i in range(1, len(close)):
        if np.isnan(atr[i - 1]):
            continue
        # Bantlar sadece trend yönünde daralır (üst bant aşağı, alt bant yukarı).
        if not (upper_basic[i] < upper[i - 1] or close[i - 1] > upper[i - 1]):
            upper[i] = upper[i - 1]
        if not (lower_basic[i] > lower[i - 1] or close[i - 1] < lower[i - 1]):
            lower[i] = lower[i - 1]
        prev = direction[i - 1] or 1
        if prev == 1 and close[i] < lower[i]:
            direction[i] = -1
        elif prev == -1 and close[i] > upper[i]:
            direction[i] = 1
        else:
            direction[i] = prev
    return direction


class SupertrendTrend(SwingRiskMixin, IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"

    st_period = IntParameter(7, 21, default=10, space="buy")
    st_multiplier = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="buy")

    def signal_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["st_dir"] = supertrend(dataframe, self.st_period.value,
                                         self.st_multiplier.value)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        prev = dataframe["st_dir"].shift(1)
        has_volume = dataframe["volume"] > 0
        dataframe.loc[(dataframe["st_dir"] == 1) & (prev == -1) & has_volume,
                      ["enter_long", "enter_tag"]] = (1, "supertrend_up")
        dataframe.loc[(dataframe["st_dir"] == -1) & (prev == 1) & has_volume,
                      ["enter_short", "enter_tag"]] = (1, "supertrend_down")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["st_dir"] == -1, "exit_long"] = 1
        dataframe.loc[dataframe["st_dir"] == 1, "exit_short"] = 1
        return dataframe
