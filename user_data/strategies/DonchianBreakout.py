"""
Strateji 2 - Kırılım: Donchian kanalı kırılımı + hacim onayı ("Turtle" tarzı).

Mantık:
  * Kapanış, önceki entry_period mumun en yükseğinin üstüne çıkarsa ve hacim
    ortalamanın vol_mult katından fazlaysa -> LONG. En düşüğün altına inerse -> SHORT.
  * Çıkış: fiyat, daha kısa (exit_period) kanalın ters ucunu kırarsa
    (veya ortak ATR stop / takip eden stop).
Parametreler: entry_period, exit_period, vol_mult (3 adet).
"""
import sys
from pathlib import Path

from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy

sys.path.append(str(Path(__file__).parent))
from swing_risk import SwingRiskMixin  # noqa: E402


class DonchianBreakout(SwingRiskMixin, IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"

    entry_period = IntParameter(15, 55, default=20, space="buy")
    exit_period = IntParameter(5, 20, default=10, space="sell")
    vol_mult = DecimalParameter(1.0, 2.0, default=1.5, decimals=1, space="buy")

    def signal_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # shift(1): kanal sadece ÖNCEKİ mumlardan hesaplanır (geleceğe bakma yok).
        for p in set(self.entry_period.range) | set(self.exit_period.range):
            dataframe[f"dc_high_{p}"] = dataframe["high"].rolling(p).max().shift(1)
            dataframe[f"dc_low_{p}"] = dataframe["low"].rolling(p).min().shift(1)
        dataframe["vol_avg"] = dataframe["volume"].rolling(20).mean().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = self.entry_period.value
        loud = dataframe["volume"] > dataframe["vol_avg"] * self.vol_mult.value
        dataframe.loc[(dataframe["close"] > dataframe[f"dc_high_{p}"]) & loud,
                      ["enter_long", "enter_tag"]] = (1, "breakout_up")
        dataframe.loc[(dataframe["close"] < dataframe[f"dc_low_{p}"]) & loud,
                      ["enter_short", "enter_tag"]] = (1, "breakout_down")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        p = self.exit_period.value
        dataframe.loc[dataframe["close"] < dataframe[f"dc_low_{p}"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] > dataframe[f"dc_high_{p}"], "exit_short"] = 1
        return dataframe
