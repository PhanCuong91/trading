"""Relative Strength Index (RSI) strategy implementation."""

from typing import List

from forex_signals.data.models import Candle, Signal


class RSIStrategy:
    """
    Relative Strength Index strategy.

    Calculates the standard RSI indicator and generates signals based on
    threshold crossings.

    BUY when RSI crosses above oversold level (default 30)
    SELL when RSI crosses below overbought level (default 70)
    """

    def __init__(
        self, period: int = 14, overbought: float = 70.0, oversold: float = 30.0
    ) -> None:
        self._period = period
        self._overbought = overbought
        self._oversold = oversold

    @property
    def name(self) -> str:
        return "RSI"

    @property
    def min_candles(self) -> int:
        """Need period price changes + 1 extra for crossing detection.

        period price changes require period + 1 candles.
        Crossing detection needs one more RSI value, so period + 2 total.
        """
        return self._period + 2

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Generate a trading signal based on RSI threshold crossings.

        Returns NEUTRAL if insufficient candles are provided.
        """
        if len(candles) < self.min_candles:
            return Signal.NEUTRAL

        # Calculate price changes
        changes = [
            candles[i].close - candles[i - 1].close
            for i in range(1, len(candles))
        ]

        # Calculate initial average gain and loss over the first 'period' changes
        initial_gains = [max(c, 0.0) for c in changes[: self._period]]
        initial_losses = [abs(min(c, 0.0)) for c in changes[: self._period]]

        avg_gain = sum(initial_gains) / self._period
        avg_loss = sum(initial_losses) / self._period

        # Calculate RSI values using smoothed averages
        rsi_values: List[float] = []
        rsi_values.append(self._compute_rsi(avg_gain, avg_loss))

        for i in range(self._period, len(changes)):
            gain = max(changes[i], 0.0)
            loss = abs(min(changes[i], 0.0))

            avg_gain = ((avg_gain * (self._period - 1)) + gain) / self._period
            avg_loss = ((avg_loss * (self._period - 1)) + loss) / self._period

            rsi_values.append(self._compute_rsi(avg_gain, avg_loss))

        # Need at least 2 RSI values for crossing detection
        if len(rsi_values) < 2:
            return Signal.NEUTRAL

        prev_rsi = rsi_values[-2]
        curr_rsi = rsi_values[-1]

        # BUY: RSI crosses above oversold level
        if prev_rsi < self._oversold and curr_rsi >= self._oversold:
            return Signal.BUY

        # SELL: RSI crosses below overbought level
        if prev_rsi > self._overbought and curr_rsi <= self._overbought:
            return Signal.SELL

        return Signal.NEUTRAL

    @staticmethod
    def _compute_rsi(avg_gain: float, avg_loss: float) -> float:
        """Compute RSI from average gain and average loss."""
        if avg_loss == 0.0:
            return 100.0 if avg_gain > 0.0 else 50.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
