"""Consensus engine for determining trade signals from strategy agreement."""

from typing import List

from forex_signals.data.models import Signal, StrategySignal


class ConsensusEngine:
    """Determines trade signal from strategy agreement.

    Counts BUY and SELL signals from all strategies. If the count for either
    direction meets or exceeds the threshold, that direction is returned.
    Otherwise, returns NEUTRAL.
    """

    def __init__(self, threshold: int = 4):
        """
        Args:
            threshold: Minimum number of strategies that must agree.
                       Default is 4 out of 5.
        """
        self.threshold = threshold

    def evaluate(self, signals: List[StrategySignal]) -> Signal:
        """
        Count BUY and SELL signals. If either count >= threshold,
        return that direction. Otherwise return NEUTRAL.

        Args:
            signals: List of strategy signals (one per strategy)

        Returns:
            Signal.BUY, Signal.SELL, or Signal.NEUTRAL
        """
        buy_count = sum(1 for s in signals if s.signal == Signal.BUY)
        sell_count = sum(1 for s in signals if s.signal == Signal.SELL)

        if buy_count >= self.threshold:
            return Signal.BUY
        if sell_count >= self.threshold:
            return Signal.SELL
        return Signal.NEUTRAL
