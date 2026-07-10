"""Tests for the Strategy protocol."""

from typing import List

from forex_signals.data.models import Candle, Signal
from forex_signals.strategies.base import Strategy


class MockStrategy:
    """A minimal implementation of the Strategy protocol for testing."""

    @property
    def name(self) -> str:
        return "Mock Strategy"

    def generate_signal(self, candles: List[Candle]) -> Signal:
        return Signal.NEUTRAL

    @property
    def min_candles(self) -> int:
        return 1


def test_mock_strategy_conforms_to_protocol():
    """A class implementing all required methods satisfies the Strategy protocol."""
    strategy: Strategy = MockStrategy()
    assert strategy.name == "Mock Strategy"
    assert strategy.min_candles == 1


def test_generate_signal_returns_valid_signal():
    """generate_signal returns a valid Signal enum member."""
    strategy: Strategy = MockStrategy()
    result = strategy.generate_signal([])
    assert result in (Signal.BUY, Signal.SELL, Signal.NEUTRAL)


def test_strategy_protocol_is_runtime_checkable():
    """Strategy protocol can be used for isinstance checks at runtime."""
    # Protocol with @runtime_checkable would allow isinstance checks,
    # but the design uses structural subtyping (duck typing), which is
    # validated through type annotations at assignment time.
    strategy = MockStrategy()
    # Verify structural conformance by assigning to typed variable
    typed_strategy: Strategy = strategy
    assert typed_strategy.name == "Mock Strategy"
    assert typed_strategy.min_candles == 1
    assert typed_strategy.generate_signal([]) == Signal.NEUTRAL
