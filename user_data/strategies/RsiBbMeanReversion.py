"""
Strateji 4 - Ortalamaya dönüş: RSI + Bollinger bandı, SADECE üst zaman
dilimindeki trend yönünde.

Mantık (1 saatlik mumlar, trend filtresi 4 saatlik mumlardan):
  * 4s trendi yukarıysa (4s kapanış > 4s EMA) ve 1s fiyatı aşırı düşmüşse
    (RSI < rsi_low ve kapanış alt Bollinger bandının altında) -> LONG
    ("yükselen trendde ucuzdan al").
  * 4s trendi aşağıysa ve fiyat aşırı yükselmişse (RSI > 100 - rsi_low ve
    kapanış üst bandın üstünde) -> SHORT.
  * Çıkış: fiyat Bollinger orta bandına dönünce (veya ortak ATR stop / takip eden stop).
Parametreler: rsi_low, bb_std, trend_ema (3 adet).
"""
import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from technical import qtpylib
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, informative

sys.path.append(str(Path(__file__).parent))
from swing_risk import SwingRiskMixin  # noqa: E402


class RsiBbMeanReversion(SwingRiskMixin, IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    startup_candle_count = 500  # 4s EMA'nın ısınması için (4 x 100+ mum)

    rsi_low = IntParameter(20, 35, default=30, space="buy")
    bb_std = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="buy")
    trend_ema = IntParameter(50, 100, default=50, space="buy", optimize=False)

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema"] = ta.EMA(dataframe, timeperiod=self.trend_ema.value)
        dataframe["uptrend"] = (dataframe["close"] > dataframe["ema"]).astype(int)
        return dataframe

    def signal_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20,
                                     stds=self.bb_std.value)
        dataframe["bb_lower"], dataframe["bb_mid"], dataframe["bb_upper"] = (
            bb["lower"], bb["mid"], bb["upper"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        up = dataframe["uptrend_4h"] == 1
        down = dataframe["uptrend_4h"] == 0
        has_volume = dataframe["volume"] > 0
        dataframe.loc[up & (dataframe["rsi"] < self.rsi_low.value)
                      & (dataframe["close"] < dataframe["bb_lower"]) & has_volume,
                      ["enter_long", "enter_tag"]] = (1, "dip_in_uptrend")
        dataframe.loc[down & (dataframe["rsi"] > 100 - self.rsi_low.value)
                      & (dataframe["close"] > dataframe["bb_upper"]) & has_volume,
                      ["enter_short", "enter_tag"]] = (1, "rally_in_downtrend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] > dataframe["bb_mid"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] < dataframe["bb_mid"], "exit_short"] = 1
        return dataframe
