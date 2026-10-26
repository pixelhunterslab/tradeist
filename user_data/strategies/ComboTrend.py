"""
Strateji 5 - Kombinasyon: EmaAdxTrend + SupertrendTrend.

Bileşenler, turnuvada SADECE in-sample (2020-2024) ve walk-forward sonuçlarına
göre seçildi (out-of-sample'a bakılmadan): EmaAdxTrend en yüksek in-sample
puanı, SupertrendTrend en tutarlı walk-forward.

Mantık (4 saatlik mumlar):
  * Trend yukarı = hızlı EMA > yavaş EMA  VE  Supertrend yukarı.
  * İki gösterge aynı yönü göstermeye BAŞLADIĞI mumda ve ADX >= adx_min ise giriş.
  * Çıkış: göstergelerden biri ters dönünce (veya ortak ATR stop / takip eden stop).
Parametreler: adx_min, st_multiplier optimize edilir (2 adet). EMA uzunlukları ve
Supertrend periyodu bileşen stratejilerin in-sample ayarından sabit alındı.
"""
import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy

sys.path.append(str(Path(__file__).parent))
from SupertrendTrend import supertrend  # noqa: E402
from swing_risk import SwingRiskMixin  # noqa: E402


class ComboTrend(SwingRiskMixin, IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"

    ema_fast = IntParameter(10, 30, default=15, space="buy", optimize=False)
    ema_slow = IntParameter(40, 100, default=77, space="buy", optimize=False)
    st_period = IntParameter(7, 21, default=18, space="buy", optimize=False)
    adx_min = IntParameter(15, 30, default=20, space="buy")
    st_multiplier = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="buy")

    def signal_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["st_dir"] = supertrend(dataframe, self.st_period.value,
                                         self.st_multiplier.value)
        dataframe["trend_up"] = ((dataframe["ema_fast"] > dataframe["ema_slow"])
                                 & (dataframe["st_dir"] == 1)).astype(int)
        dataframe["trend_down"] = ((dataframe["ema_fast"] < dataframe["ema_slow"])
                                   & (dataframe["st_dir"] == -1)).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        strong = dataframe["adx"] >= self.adx_min.value
        has_volume = dataframe["volume"] > 0
        new_up = (dataframe["trend_up"] == 1) & (dataframe["trend_up"].shift(1) == 0)
        new_down = (dataframe["trend_down"] == 1) & (dataframe["trend_down"].shift(1) == 0)
        dataframe.loc[new_up & strong & has_volume, ["enter_long", "enter_tag"]] = (1, "combo_up")
        dataframe.loc[new_down & strong & has_volume,
                      ["enter_short", "enter_tag"]] = (1, "combo_down")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["trend_up"] == 0, "exit_long"] = 1
        dataframe.loc[dataframe["trend_down"] == 0, "exit_short"] = 1
        return dataframe
