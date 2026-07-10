"""Stochastic Momentum Index (SMI) strategy implementation."""

from typing import List

from forex_signals.data.models import Candle, Signal


class SMIStrategy:
    """
    Stochastic Momentum Index strategy.

    Calculates the distance of close from the midpoint of the high-low range,
    smoothed with double EMA. Generates signals on threshold crossings.

    BUY when SMI crosses above -40 (oversold recovery)
    SELL when SMI crosses below +40 (overbought reversal)
    """

    def __init__(self, period: int = 14, smooth_period: int = 3) -> None:
        self._period = period
        self._smooth_period = smooth_period

    @property
    def name(self) -> str:
        return "SMI"

    @property
    def min_candles(self) -> int:
        """Need period + 2*smooth_period candles for valid double EMA."""
        return self._period + 2 * self._smooth_period

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Generate a trading signal based on SMI threshold crossings.

        Returns NEUTRAL if insufficient candles are provided.
        """
        if len(candles) < self.min_candles:
            return Signal.NEUTRAL

        # Calculate raw distance and range series
        distances: List[float] = []
        ranges: List[float] = []

        for i in range(self._period - 1, len(candles)):
            window = candles[i - self._period + 1 : i + 1]
            highest_high = max(c.high for c in window)
            lowest_low = min(c.low for c in window)
            midpoint = (highest_high + lowest_low) / 2.0
            distance = candles[i].close - midpoint
            range_val = highest_high - lowest_low

            distances.append(distance)
            ranges.append(range_val)

        # Apply double EMA smoothing to distances and ranges
        smoothed_distances = self._double_ema(distances, self._smooth_period)
        smoothed_ranges = self._double_ema(ranges, self._smooth_period)

        # Calculate SMI values from the smoothed series
        smi_values: List[float] = []
        for sd, sr in zip(smoothed_distances, smoothed_ranges):
            half_range = sr / 2.0
            if half_range == 0.0:
                smi_values.append(0.0)
            else:
                smi_values.append(100.0 * (sd / half_range))

        # Need at least 2 SMI values for crossing detection
        if len(smi_values) < 2:
            return Signal.NEUTRAL

        prev_smi = smi_values[-2]
        curr_smi = smi_values[-1]

        # BUY: SMI crosses above -40
        if prev_smi < -40.0 and curr_smi >= -40.0:
            return Signal.BUY

        # SELL: SMI crosses below +40
        if prev_smi > 40.0 and curr_smi <= 40.0:
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

    @classmethod
    def _double_ema(cls, values: List[float], period: int) -> List[float]:
        """Apply EMA twice (double smoothing)."""
        first_ema = cls._ema(values, period)
        second_ema = cls._ema(first_ema, period)
        return second_ema
