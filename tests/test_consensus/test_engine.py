"""Unit tests for the ConsensusEngine."""

from datetime import datetime

import pytest

from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import Signal, StrategySignal


def _make_signal(name: str, signal: Signal) -> StrategySignal:
    """Helper to create a StrategySignal with a fixed timestamp."""
    return StrategySignal(
        strategy_name=name,
        signal=signal,
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
    )


STRATEGY_NAMES = ["smi", "moving_average", "rsi", "macd", "bollinger"]


class TestConsensusEngine:
    """Tests for ConsensusEngine.evaluate()."""

    def test_default_threshold_is_4(self):
        engine = ConsensusEngine()
        assert engine.threshold == 4

    def test_custom_threshold(self):
        engine = ConsensusEngine(threshold=3)
        assert engine.threshold == 3

    def test_all_buy_returns_buy(self):
        """5 out of 5 BUY signals should return BUY."""
        engine = ConsensusEngine(threshold=4)
        signals = [_make_signal(name, Signal.BUY) for name in STRATEGY_NAMES]
        assert engine.evaluate(signals) == Signal.BUY

    def test_all_sell_returns_sell(self):
        """5 out of 5 SELL signals should return SELL."""
        engine = ConsensusEngine(threshold=4)
        signals = [_make_signal(name, Signal.SELL) for name in STRATEGY_NAMES]
        assert engine.evaluate(signals) == Signal.SELL

    def test_4_buy_1_neutral_returns_buy(self):
        """4 BUY + 1 NEUTRAL meets threshold → BUY."""
        engine = ConsensusEngine(threshold=4)
        signals = [
            _make_signal("smi", Signal.BUY),
            _make_signal("moving_average", Signal.BUY),
            _make_signal("rsi", Signal.BUY),
            _make_signal("macd", Signal.BUY),
            _make_signal("bollinger", Signal.NEUTRAL),
        ]
        assert engine.evaluate(signals) == Signal.BUY

    def test_4_sell_1_neutral_returns_sell(self):
        """4 SELL + 1 NEUTRAL meets threshold → SELL."""
        engine = ConsensusEngine(threshold=4)
        signals = [
            _make_signal("smi", Signal.SELL),
            _make_signal("moving_average", Signal.SELL),
            _make_signal("rsi", Signal.SELL),
            _make_signal("macd", Signal.SELL),
            _make_signal("bollinger", Signal.NEUTRAL),
        ]
        assert engine.evaluate(signals) == Signal.SELL

    def test_3_buy_2_sell_returns_neutral(self):
        """3 BUY + 2 SELL → below threshold → NEUTRAL."""
        engine = ConsensusEngine(threshold=4)
        signals = [
            _make_signal("smi", Signal.BUY),
            _make_signal("moving_average", Signal.BUY),
            _make_signal("rsi", Signal.BUY),
            _make_signal("macd", Signal.SELL),
            _make_signal("bollinger", Signal.SELL),
        ]
        assert engine.evaluate(signals) == Signal.NEUTRAL

    def test_3_buy_2_neutral_returns_neutral(self):
        """3 BUY + 2 NEUTRAL → below threshold → NEUTRAL."""
        engine = ConsensusEngine(threshold=4)
        signals = [
            _make_signal("smi", Signal.BUY),
            _make_signal("moving_average", Signal.BUY),
            _make_signal("rsi", Signal.BUY),
            _make_signal("macd", Signal.NEUTRAL),
            _make_signal("bollinger", Signal.NEUTRAL),
        ]
        assert engine.evaluate(signals) == Signal.NEUTRAL

    def test_all_neutral_returns_neutral(self):
        """All NEUTRAL → NEUTRAL."""
        engine = ConsensusEngine(threshold=4)
        signals = [_make_signal(name, Signal.NEUTRAL) for name in STRATEGY_NAMES]
        assert engine.evaluate(signals) == Signal.NEUTRAL

    def test_empty_signals_returns_neutral(self):
        """No signals → NEUTRAL."""
        engine = ConsensusEngine(threshold=4)
        assert engine.evaluate([]) == Signal.NEUTRAL

    def test_threshold_3_with_3_buy(self):
        """Custom threshold of 3: 3 BUY signals should return BUY."""
        engine = ConsensusEngine(threshold=3)
        signals = [
            _make_signal("smi", Signal.BUY),
            _make_signal("moving_average", Signal.BUY),
            _make_signal("rsi", Signal.BUY),
            _make_signal("macd", Signal.NEUTRAL),
            _make_signal("bollinger", Signal.SELL),
        ]
        assert engine.evaluate(signals) == Signal.BUY

    def test_order_does_not_matter(self):
        """Signal order in list should not affect result (equal weight)."""
        engine = ConsensusEngine(threshold=4)
        signals_ordered = [
            _make_signal("smi", Signal.BUY),
            _make_signal("moving_average", Signal.BUY),
            _make_signal("rsi", Signal.BUY),
            _make_signal("macd", Signal.BUY),
            _make_signal("bollinger", Signal.SELL),
        ]
        signals_reversed = list(reversed(signals_ordered))
        assert engine.evaluate(signals_ordered) == engine.evaluate(signals_reversed)
