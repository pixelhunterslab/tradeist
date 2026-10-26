"""
Strateji 1 - Trend takibi: EMA kesişimi + ADX trend gücü filtresi.

Mantık:
  * Hızlı EMA yavaş EMA'yı yukarı keserse ve ADX >= adx_min ise (gerçek bir
    trend var) -> LONG.  Aşağı keserse -> SHORT.
  * Çıkış: ters yönde kesişim (veya ortak ATR stop / takip eden stop).
Parametreler: ema_fast, ema_slow, adx_min (3 adet).
"""
import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from technical import qtpylib
from freqtrade.strategy import IntParameter, IStrategy

sys.path.append(str(Path(__file__).parent))
from swing_risk import SwingRiskMixin  # noqa: E402


class EmaAdxTrend(SwingRiskMixin, IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"

    ema_fast = IntParameter(10, 30, default=20, space="buy")
    ema_slow = IntParameter(40, 100, default=50, space="buy")
    adx_min = IntParameter(15, 30, default=20, space="buy")

    def signal_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for period in set(self.ema_fast.range) | set(self.ema_slow.range):
            dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe[f"ema_{self.ema_fast.value}"]
        slow = dataframe[f"ema_{self.ema_slow.value}"]
        strong = dataframe["adx"] >= self.adx_min.value
        has_volume = dataframe["volume"] > 0
        dataframe.loc[qtpylib.crossed_above(fast, slow) & strong & has_volume,
                      ["enter_long", "enter_tag"]] = (1, "ema_cross_up")
        dataframe.loc[qtpylib.crossed_below(fast, slow) & strong & has_volume,
                      ["enter_short", "enter_tag"]] = (1, "ema_cross_down")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe[f"ema_{self.ema_fast.value}"]
        slow = dataframe[f"ema_{self.ema_slow.value}"]
        dataframe.loc[qtpylib.crossed_below(fast, slow), "exit_long"] = 1
        dataframe.loc[qtpylib.crossed_above(fast, slow), "exit_short"] = 1
        return dataframe
