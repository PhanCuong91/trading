"""MACD (Moving Average Convergence Divergence) strategy implementation."""

from typing import List

from forex_signals.data.models import Candle, Signal


class MACDStrategy:
    """
    MACD strategy using standard (12, 26, 9) parameters.

    MACD Line = EMA(close, fast_period) - EMA(close, slow_period)
    Signal Line = EMA(MACD Line, signal_period)

    BUY when MACD line crosses above signal line.
    SELL when MACD line crosses below signal line.
    NEUTRAL when no crossover or insufficient data.
    """

    def __init__(
        self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._signal_period = signal_period

    @property
    def name(self) -> str:
        return "MACD"

    @property
    def min_candles(self) -> int:
        """Need slow_period + signal_period candles for valid calculation + crossing detection."""
        return self._slow_period + self._signal_period

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Generate a trading signal based on MACD/signal line crossovers.

        Returns NEUTRAL if insufficient candles are provided.
        """
        if len(candles) < self.min_candles:
            return Signal.NEUTRAL

        closes = [c.close for c in candles]

        # Calculate MACD line: EMA(fast) - EMA(slow)
        fast_ema = self._ema(closes, self._fast_period)
        slow_ema = self._ema(closes, self._slow_period)

        # MACD line starts from index where slow EMA is valid (all indices since EMA
        # is computed from the start, but needs slow_period data to stabilize)
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]

        # Signal line: EMA of MACD line
        signal_line = self._ema(macd_line, self._signal_period)

        # Need at least 2 values for crossing detection
        if len(signal_line) < 2:
            return Signal.NEUTRAL

        prev_macd = macd_line[-2]
        curr_macd = macd_line[-1]
        prev_signal = signal_line[-2]
        curr_signal = signal_line[-1]

        # BUY: MACD crosses above signal line
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            return Signal.BUY

        # SELL: MACD crosses below signal line
        if prev_macd >= prev_signal and curr_macd < curr_signal:
            return Signal.SELL

        return Signal.NEUTRAL

    @staticmethod
    def _ema(values: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average."""
        if not values:
            return []

        multiplier = 2.0 / (period + 1)
        result = [values[0]]

        for i in range(1, len(values)):
            ema_val = (values[i] - result[-1]) * multiplier + result[-1]
            result.append(ema_val)

        return result
