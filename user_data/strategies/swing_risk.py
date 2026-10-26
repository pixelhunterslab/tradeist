"""
Tüm stratejilerin ortak risk kuralları (tek yerde, kopyala-yapıştır yok).

Bir strateji bunu şöyle kullanır:

    class BenimStratejim(SwingRiskMixin, IStrategy):
        def signal_indicators(self, dataframe, metadata): ...
        def populate_entry_trend(self, dataframe, metadata): ...
        def populate_exit_trend(self, dataframe, metadata): ...

Kurallar (değerler config.json -> "swing_risk", .env ile değiştirilebilir):

1. STOP = giriş fiyatı -/+ atr_stop_multiplier x ATR (giriş sinyali mumundaki ATR).
   Sabit yüzde değil; piyasa oynaksa stop uzak, sakinse yakın. Ama en az
   min_stop_distance_pct (veri boşluğu / aşırı sakin piyasada saçma derecede
   dar stopları önler).
2. POZİSYON BÜYÜKLÜĞÜ: stop olursa kayıp = bakiyenin en fazla
   max_loss_per_trade_pct_of_balance %'si olacak şekilde hesaplanır.
   Stop uzaksa pozisyon küçük, yakınsa büyük.
3. SINIRLAR: tek işlemin marjini bakiyenin en fazla
   max_margin_per_trade_pct_of_balance %'si; kaldıraç en fazla max_leverage.
   Sınır aşılırsa pozisyon küçültülür (risk %5'in altında kalır). Binance'in
   minimum emrinin altına düşerse işlem atlanır.
4. LİKİDASYON PAYI: kaldıraç, stop likidasyon mesafesinin en fazla
   %(100 - liquidation_buffer) kadarında kalacak şekilde gerekirse düşürülür.
5. ÇIKIŞ (exit_mode):
   - "trailing": kâr 'trail_activation_rr' x risk'e ulaşınca stop, görülen en iyi
     fiyatın trail_atr_multiplier x ATR gerisinden takip eder (kazananlar koşar).
   - "fixed_tp": fiyat giriş +/- take_profit_rr x risk'e gelince kâr alınır.
   Her iki modda da stratejinin kendi çıkış sinyali ve ATR stop geçerlidir.
"""
from datetime import datetime, timedelta
from math import floor

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.exchange import timeframe_to_minutes, timeframe_to_prev_date
from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

DEFAULT_RISK = {
    "leverage": 5,
    "max_leverage": 5,
    "max_loss_per_trade_pct_of_balance": 5.0,
    "max_margin_per_trade_pct_of_balance": 25.0,
    "atr_period": 14,
    "atr_stop_multiplier": 2.5,
    "min_stop_distance_pct": 1.0,
    "exit_mode": "trailing",
    "take_profit_rr": 2.0,
    "trail_activation_rr": 1.0,
    "trail_atr_multiplier": 2.5,
}
# Binance'in küçük pozisyonlardaki bakım marjini ~%0.4-0.5; ihtiyatlı olmak için %1.
MAINTENANCE_MARGIN_SAFETY = 0.01


class SwingRiskMixin:
    # ---- Freqtrade ayarları: tüm stratejilerde aynı ----
    can_short = True
    use_custom_stoploss = True
    trailing_stop = False           # takip eden stop custom_stoploss içinde (ATR tabanlı)
    minimal_roi = {"0": 100}        # sabit % kâr al kapalı; çıkışları biz yönetiyoruz
    # Acil durum tavanı (kaldıraçlı oran). Gerçek stop custom_stoploss'ta hesaplanır.
    stoploss = -0.75
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    startup_candle_count = 300

    # ------------------------------------------------------------------ ayarlar
    @property
    def risk(self) -> dict:
        if not hasattr(self, "_risk"):
            cfg = {**DEFAULT_RISK, **self.config.get("swing_risk", {})}
            cfg["leverage"] = min(float(cfg["leverage"]), float(cfg["max_leverage"]))
            self._risk = cfg
        return self._risk

    # ------------------------------------------------------------- göstergeler
    def signal_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Strateji kendi göstergelerini burada ekler."""
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.signal_indicators(dataframe, metadata)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=int(self.risk["atr_period"]))
        return dataframe

    # ---------------------------------------------------------------- yardımcı
    def _last_candle(self, pair: str):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df.iloc[-1] if len(df) else None

    def _risk_distance(self, atr: float, price: float) -> float:
        """Girişten stopa fiyat mesafesi (fiyat birimi cinsinden)."""
        return max(self.risk["atr_stop_multiplier"] * atr,
                   self.risk["min_stop_distance_pct"] / 100 * price)

    def _stop_fraction(self, candle) -> float | None:
        """Stop mesafesi, fiyatın oranı olarak (örn. 0.04 = %4)."""
        if candle is None or not candle["atr"] > 0 or not candle["close"] > 0:
            return None
        return self._risk_distance(candle["atr"], candle["close"]) / candle["close"]

    def _entry_atr(self, pair: str, trade: Trade) -> float | None:
        """Giriş sinyali mumundaki ATR (işlem boyunca sabit, trade'e kaydedilir)."""
        atr = trade.get_custom_data("entry_atr")
        if atr:
            return atr
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        signal_candle = timeframe_to_prev_date(self.timeframe, trade.open_date_utc) - timedelta(
            minutes=timeframe_to_minutes(self.timeframe)
        )
        rows = df.loc[df["date"] == signal_candle, "atr"]
        if rows.empty or not rows.iloc[0] > 0:
            return None
        atr = float(rows.iloc[0])
        trade.set_custom_data("entry_atr", atr)
        return atr

    # -------------------------------------------------------------- kaldıraç
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        lev = min(self.risk["leverage"], max_leverage)
        stop = self._stop_fraction(self._last_candle(pair))
        if stop:
            # Likidasyon mesafesi ~ 1/kaldıraç - bakım marjini. Stop bu mesafenin
            # en fazla (1 - buffer) kadarında olmalı.
            keep = 1 - float(self.config.get("liquidation_buffer", 0.3))
            lev_cap = 1 / (stop / keep + MAINTENANCE_MARGIN_SAFETY)
            lev = min(lev, lev_cap)
        return max(1.0, float(floor(lev)))

    # ---------------------------------------------------- pozisyon büyüklüğü
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        stop = self._stop_fraction(self._last_candle(pair))
        if not stop:
            return 0  # ATR yoksa işlem yok
        balance = self.wallets.get_total_stake_amount()
        risk_usdt = balance * self.risk["max_loss_per_trade_pct_of_balance"] / 100
        notional = risk_usdt / stop                 # stop olursa kayıp = risk_usdt
        margin = notional / leverage
        margin_cap = balance * self.risk["max_margin_per_trade_pct_of_balance"] / 100
        margin = min(margin, margin_cap, max_stake)
        if min_stake is not None and margin < min_stake:
            return 0  # Binance minimum emrinin altında -> işlemi atla
        return margin

    # ------------------------------------------------------------------- stop
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        atr = self._entry_atr(pair, trade)
        if not atr:
            return None
        risk_dist = self._risk_distance(atr, trade.open_rate)
        direction = -1 if trade.is_short else 1
        stop_price = trade.open_rate - direction * risk_dist

        if self.risk["exit_mode"] == "trailing":
            activation = self.risk["trail_activation_rr"] * risk_dist
            trail = self.risk["trail_atr_multiplier"] * atr
            # max_rate/min_rate: işlem açıldığından beri görülen en yüksek/en düşük fiyat
            best_high = trade.max_rate or trade.open_rate
            best_low = trade.min_rate or trade.open_rate
            if not trade.is_short and best_high >= trade.open_rate + activation:
                stop_price = max(stop_price, best_high - trail)
            elif trade.is_short and best_low <= trade.open_rate - activation:
                stop_price = min(stop_price, best_low + trail)

        return stoploss_from_absolute(stop_price, current_rate, is_short=trade.is_short,
                                      leverage=trade.leverage)

    # ------------------------------------------------------------- kâr al
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> str | None:
        if self.risk["exit_mode"] != "fixed_tp":
            return None
        atr = self._entry_atr(pair, trade)
        if not atr:
            return None
        target = self.risk["take_profit_rr"] * self._risk_distance(atr, trade.open_rate)
        if not trade.is_short and current_rate >= trade.open_rate + target:
            return "take_profit"
        if trade.is_short and current_rate <= trade.open_rate - target:
            return "take_profit"
        return None
