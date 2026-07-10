"""Bollinger Bands strategy implementation."""

import math
from typing import List

from forex_signals.data.models import Candle, Signal


class BollingerBandsStrategy:
    """
    Bollinger Bands strategy.

    Uses a Simple Moving Average (SMA) with configurable standard deviation bands.
    Generates signals based on price touching/crossing bands and reversing.

    BUY when price touches/crosses below the lower band and reverses up.
    SELL when price touches/crosses above the upper band and reverses down.
    NEUTRAL otherwise.
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        self._period = period
        self._std_dev = std_dev

    @property
    def name(self) -> str:
        return "Bollinger Bands"

    @property
    def min_candles(self) -> int:
        """Need period + 1 candles to detect reversal (previous candle's relationship to bands)."""
        return self._period + 1

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Generate a trading signal based on Bollinger Bands reversal detection.

        Returns NEUTRAL if insufficient candles are provided.

        BUY signal: previous candle's low touched/crossed below the lower band
                    AND current candle closed above the lower band (reversal up).
        SELL signal: previous candle's high touched/crossed above the upper band
                     AND current candle closed below the upper band (reversal down).
        """
        if len(candles) < self.min_candles:
            return Signal.NEUTRAL

        # Calculate bands using the most recent `period` candles (up to current)
        current_window = candles[-self._period :]
        middle_band = self._sma(current_window)
        std = self._population_std(current_window, middle_band)
        upper_band = middle_band + self._std_dev * std
        lower_band = middle_band - self._std_dev * std

        prev_candle = candles[-2]
        curr_candle = candles[-1]

        # BUY: previous candle's low touched/crossed below lower band
        # AND current candle closed above lower band (reversal up)
        if prev_candle.low <= lower_band and curr_candle.close > lower_band:
            return Signal.BUY

        # SELL: previous candle's high touched/crossed above upper band
        # AND current candle closed below upper band (reversal down)
        if prev_candle.high >= upper_band and curr_candle.close < upper_band:
            return Signal.SELL

        return Signal.NEUTRAL

    @staticmethod
    def _sma(candles: List[Candle]) -> float:
        """Calculate Simple Moving Average of close prices."""
        return sum(c.close for c in candles) / len(candles)

    @staticmethod
    def _population_std(candles: List[Candle], mean: float) -> float:
        """Calculate population standard deviation of close prices."""
        variance = sum((c.close - mean) ** 2 for c in candles) / len(candles)
        return math.sqrt(variance)
