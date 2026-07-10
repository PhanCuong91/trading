"""Strategy protocol defining the interface all trading strategies must implement."""

from typing import List, Protocol

from forex_signals.data.models import Candle, Signal


class Strategy(Protocol):
    """All strategies implement this interface."""

    @property
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Given a sequence of historical candles (most recent last),
        produce a BUY, SELL, or NEUTRAL signal.

        Requires: len(candles) >= self.min_candles
        Returns: Signal enum value
        """
        ...

    @property
    def min_candles(self) -> int:
        """Minimum number of candles required to produce a signal."""
        ...
