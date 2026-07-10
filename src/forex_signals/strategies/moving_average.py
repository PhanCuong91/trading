"""Moving Average Crossover strategy implementation."""

from typing import List

from forex_signals.data.models import Candle, Signal


class MovingAverageCrossoverStrategy:
    """
    Moving Average Crossover strategy.

    Uses Simple Moving Average (SMA) with configurable fast and slow periods.
    Generates signals based on crossover detection.

    BUY on golden cross (fast MA crosses above slow MA)
    SELL on death cross (fast MA crosses below slow MA)
    NEUTRAL when no crossover on current candle
    """

    def __init__(self, fast_period: int = 10, slow_period: int = 50) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period

    @property
    def name(self) -> str:
        return "MA Crossover"

    @property
    def min_candles(self) -> int:
        """Need slow_period + 1 candles to compute two consecutive SMA values for crossover detection."""
        return self._slow_period + 1

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Generate a trading signal based on MA crossover detection.

        Returns NEUTRAL if insufficient candles are provided.
        """
        if len(candles) < self.min_candles:
            return Signal.NEUTRAL

        # Compute fast and slow SMA for the current and previous candle
        curr_fast = self._sma(candles, self._fast_period, offset=0)
        prev_fast = self._sma(candles, self._fast_period, offset=1)
        curr_slow = self._sma(candles, self._slow_period, offset=0)
        prev_slow = self._sma(candles, self._slow_period, offset=1)

        # Golden cross: fast crosses above slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return Signal.BUY

        # Death cross: fast crosses below slow
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return Signal.SELL

        return Signal.NEUTRAL

    @staticmethod
    def _sma(candles: List[Candle], period: int, offset: int = 0) -> float:
        """
        Calculate Simple Moving Average over the given period.

        Args:
            candles: List of candles (most recent last).
            period: Number of candles to average.
            offset: How many candles back from the end to compute.
                    offset=0 means ending at the last candle,
                    offset=1 means ending at the second-to-last candle.
        """
        end_index = len(candles) - offset
        start_index = end_index - period
        window = candles[start_index:end_index]
        return sum(c.close for c in window) / period
