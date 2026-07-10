"""Tests for the Moving Average Crossover strategy."""

from datetime import datetime, timedelta
from typing import List

import pytest

from forex_signals.data.models import Candle, Signal
from forex_signals.strategies.base import Strategy
from forex_signals.strategies.moving_average import MovingAverageCrossoverStrategy


def _make_candle(
    close: float,
    index: int = 0,
    base_time: datetime = datetime(2024, 1, 1),
) -> Candle:
    return Candle(
        timestamp=base_time + timedelta(minutes=5 * index),
        open=close,
        high=close + 0.01,
        low=close - 0.01,
        close=close,
        volume=100.0,
    )


def _make_candles_from_closes(closes: List[float]) -> List[Candle]:
    """Create candles from a list of close prices."""
    return [_make_candle(close=c, index=i) for i, c in enumerate(closes)]


class TestMovingAverageCrossoverProtocol:
    """Test that MovingAverageCrossoverStrategy conforms to Strategy protocol."""

    def test_conforms_to_strategy_protocol(self):
        strategy: Strategy = MovingAverageCrossoverStrategy()
        assert strategy.name == "MA Crossover"
        assert strategy.min_candles > 0

    def test_name_property(self):
        strategy = MovingAverageCrossoverStrategy()
        assert strategy.name == "MA Crossover"

    def test_min_candles_default(self):
        strategy = MovingAverageCrossoverStrategy()
        # slow_period(50) + 1 = 51
        assert strategy.min_candles == 51

    def test_min_candles_custom(self):
        strategy = MovingAverageCrossoverStrategy(fast_period=5, slow_period=20)
        # 20 + 1 = 21
        assert strategy.min_candles == 21


class TestMovingAverageInsufficientData:
    """Test NEUTRAL signal when insufficient candles."""

    def test_empty_candles(self):
        strategy = MovingAverageCrossoverStrategy()
        assert strategy.generate_signal([]) == Signal.NEUTRAL

    def test_fewer_than_min_candles(self):
        strategy = MovingAverageCrossoverStrategy(fast_period=5, slow_period=20)
        candles = _make_candles_from_closes([1.0] * 20)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_exactly_one_less_than_min(self):
        strategy = MovingAverageCrossoverStrategy(fast_period=5, slow_period=20)
        candles = _make_candles_from_closes([1.0] * 20)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL


class TestMovingAverageBuySignal:
    """Test BUY signal generation (golden cross)."""

    def test_golden_cross(self):
        """Fast MA crossing above slow MA should generate BUY."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        # Need 6 candles (slow_period + 1)
        # Design prices so that:
        #   - Previous candle: fast SMA <= slow SMA
        #   - Current candle: fast SMA > slow SMA
        # Candles: indices 0..5
        # Current (last): slow SMA = avg(c[1..5]), fast SMA = avg(c[3..5])
        # Previous: slow SMA = avg(c[0..4]), fast SMA = avg(c[2..4])
        #
        # Use low prices early, high price at end for golden cross
        closes = [1.0, 1.0, 1.0, 1.0, 1.0, 1.5]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.0, 1.0, 1.0) = 1.0
        # prev_slow = avg(1.0, 1.0, 1.0, 1.0, 1.0) = 1.0
        # curr_fast = avg(1.0, 1.0, 1.5) = 1.1667
        # curr_slow = avg(1.0, 1.0, 1.0, 1.0, 1.5) = 1.1
        # prev_fast <= prev_slow (1.0 <= 1.0) ✓
        # curr_fast > curr_slow (1.1667 > 1.1) ✓
        result = strategy.generate_signal(candles)
        assert result == Signal.BUY

    def test_golden_cross_gradual(self):
        """Gradual uptrend causing golden cross should generate BUY."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        # Prices trend up at end: fast MA accelerates past slow MA
        closes = [1.0, 1.0, 1.0, 1.1, 1.2, 1.4]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.0, 1.1, 1.2) = 1.1
        # prev_slow = avg(1.0, 1.0, 1.0, 1.1, 1.2) = 1.06
        # curr_fast = avg(1.1, 1.2, 1.4) = 1.2333
        # curr_slow = avg(1.0, 1.0, 1.1, 1.2, 1.4) = 1.14
        # prev_fast > prev_slow already, so no crossover
        # Need to pick values where prev_fast <= prev_slow
        closes = [1.0, 1.0, 1.2, 1.0, 0.9, 1.5]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.2, 1.0, 0.9) = 1.0333
        # prev_slow = avg(1.0, 1.0, 1.2, 1.0, 0.9) = 1.02
        # curr_fast = avg(1.0, 0.9, 1.5) = 1.1333
        # curr_slow = avg(1.0, 1.2, 1.0, 0.9, 1.5) = 1.12
        # prev_fast(1.0333) > prev_slow(1.02) — still not a cross
        # Let me design this more carefully
        closes = [1.2, 1.1, 1.0, 0.9, 0.8, 1.3]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.0, 0.9, 0.8) = 0.9
        # prev_slow = avg(1.2, 1.1, 1.0, 0.9, 0.8) = 1.0
        # curr_fast = avg(0.9, 0.8, 1.3) = 1.0
        # curr_slow = avg(1.1, 1.0, 0.9, 0.8, 1.3) = 1.02
        # prev_fast(0.9) <= prev_slow(1.0) ✓
        # curr_fast(1.0) > curr_slow(1.02)? No, 1.0 < 1.02

        # Let's use a bigger jump
        closes = [1.2, 1.1, 1.0, 0.9, 0.8, 1.5]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.0, 0.9, 0.8) = 0.9
        # prev_slow = avg(1.2, 1.1, 1.0, 0.9, 0.8) = 1.0
        # curr_fast = avg(0.9, 0.8, 1.5) = 1.0667
        # curr_slow = avg(1.1, 1.0, 0.9, 0.8, 1.5) = 1.06
        # prev_fast(0.9) <= prev_slow(1.0) ✓
        # curr_fast(1.0667) > curr_slow(1.06) ✓
        result = strategy.generate_signal(candles)
        assert result == Signal.BUY


class TestMovingAverageSellSignal:
    """Test SELL signal generation (death cross)."""

    def test_death_cross(self):
        """Fast MA crossing below slow MA should generate SELL."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        # Design prices so that:
        #   - Previous candle: fast SMA >= slow SMA
        #   - Current candle: fast SMA < slow SMA
        closes = [0.8, 0.9, 1.0, 1.1, 1.2, 0.5]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.0, 1.1, 1.2) = 1.1
        # prev_slow = avg(0.8, 0.9, 1.0, 1.1, 1.2) = 1.0
        # curr_fast = avg(1.1, 1.2, 0.5) = 0.9333
        # curr_slow = avg(0.9, 1.0, 1.1, 1.2, 0.5) = 0.94
        # prev_fast(1.1) >= prev_slow(1.0) ✓
        # curr_fast(0.9333) < curr_slow(0.94) ✓
        result = strategy.generate_signal(candles)
        assert result == Signal.SELL

    def test_death_cross_sharp_drop(self):
        """Sharp drop causing death cross should generate SELL."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        closes = [1.0, 1.0, 1.0, 1.0, 1.0, 0.5]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.0, 1.0, 1.0) = 1.0
        # prev_slow = avg(1.0, 1.0, 1.0, 1.0, 1.0) = 1.0
        # curr_fast = avg(1.0, 1.0, 0.5) = 0.8333
        # curr_slow = avg(1.0, 1.0, 1.0, 1.0, 0.5) = 0.9
        # prev_fast(1.0) >= prev_slow(1.0) ✓
        # curr_fast(0.8333) < curr_slow(0.9) ✓
        result = strategy.generate_signal(candles)
        assert result == Signal.SELL


class TestMovingAverageNeutralSignal:
    """Test NEUTRAL signal when no crossover occurs."""

    def test_flat_market_returns_neutral(self):
        """Flat market should return NEUTRAL."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        candles = _make_candles_from_closes([1.0] * 6)
        # Both MAs are equal, no crossover
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_fast_already_above_slow(self):
        """If fast is above slow on both candles (no crossover), return NEUTRAL."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        # Consistent uptrend — fast stays above slow
        closes = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.2, 1.3, 1.4) = 1.3
        # prev_slow = avg(1.0, 1.1, 1.2, 1.3, 1.4) = 1.2
        # curr_fast = avg(1.3, 1.4, 1.5) = 1.4
        # curr_slow = avg(1.1, 1.2, 1.3, 1.4, 1.5) = 1.3
        # prev_fast(1.3) > prev_slow(1.2) — no cross needed
        result = strategy.generate_signal(candles)
        assert result == Signal.NEUTRAL

    def test_fast_already_below_slow(self):
        """If fast is below slow on both candles (no crossover), return NEUTRAL."""
        strategy = MovingAverageCrossoverStrategy(fast_period=3, slow_period=5)
        # Consistent downtrend — fast stays below slow
        closes = [1.5, 1.4, 1.3, 1.2, 1.1, 1.0]
        candles = _make_candles_from_closes(closes)

        # prev_fast = avg(1.3, 1.2, 1.1) = 1.2
        # prev_slow = avg(1.5, 1.4, 1.3, 1.2, 1.1) = 1.3
        # curr_fast = avg(1.2, 1.1, 1.0) = 1.1
        # curr_slow = avg(1.4, 1.3, 1.2, 1.1, 1.0) = 1.2
        # prev_fast(1.2) < prev_slow(1.3) — stays below, no cross
        result = strategy.generate_signal(candles)
        assert result == Signal.NEUTRAL


class TestMovingAverageParameters:
    """Test parameter configuration."""

    def test_default_parameters(self):
        strategy = MovingAverageCrossoverStrategy()
        assert strategy._fast_period == 10
        assert strategy._slow_period == 50

    def test_custom_parameters(self):
        strategy = MovingAverageCrossoverStrategy(fast_period=5, slow_period=20)
        assert strategy._fast_period == 5
        assert strategy._slow_period == 20
