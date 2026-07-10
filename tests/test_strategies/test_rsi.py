"""Tests for the RSI strategy."""

from datetime import datetime, timedelta
from typing import List

import pytest

from forex_signals.data.models import Candle, Signal
from forex_signals.strategies.base import Strategy
from forex_signals.strategies.rsi import RSIStrategy


def _make_candle(
    close: float,
    index: int = 0,
    high: float = 0.0,
    low: float = 0.0,
    open_: float = 1.0,
    volume: float = 100.0,
    base_time: datetime = datetime(2024, 1, 1),
) -> Candle:
    # Default high/low to close +/- small offset if not specified
    if high == 0.0:
        high = close + 0.001
    if low == 0.0:
        low = close - 0.001
    return Candle(
        timestamp=base_time + timedelta(minutes=5 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_candles_from_closes(closes: List[float]) -> List[Candle]:
    """Create candles from a list of close prices."""
    return [_make_candle(close=c, index=i) for i, c in enumerate(closes)]


class TestRSIStrategyProtocol:
    """Test that RSIStrategy conforms to Strategy protocol."""

    def test_conforms_to_strategy_protocol(self):
        strategy: Strategy = RSIStrategy()
        assert strategy.name == "RSI"
        assert strategy.min_candles > 0

    def test_name_property(self):
        strategy = RSIStrategy()
        assert strategy.name == "RSI"

    def test_min_candles_default(self):
        strategy = RSIStrategy(period=14)
        # period + 2 = 16
        assert strategy.min_candles == 16

    def test_min_candles_custom(self):
        strategy = RSIStrategy(period=10)
        # 10 + 2 = 12
        assert strategy.min_candles == 12


class TestRSIInsufficientData:
    """Test NEUTRAL signal when insufficient candles."""

    def test_empty_candles(self):
        strategy = RSIStrategy()
        assert strategy.generate_signal([]) == Signal.NEUTRAL

    def test_fewer_than_min_candles(self):
        strategy = RSIStrategy(period=14)
        candles = _make_candles_from_closes([1.0] * 15)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_exactly_min_candles_returns_valid_signal(self):
        strategy = RSIStrategy(period=14)
        candles = _make_candles_from_closes([1.0] * 16)
        result = strategy.generate_signal(candles)
        assert result in (Signal.BUY, Signal.SELL, Signal.NEUTRAL)


class TestRSIBuySignal:
    """Test BUY signal generation (RSI crossing above oversold)."""

    def test_buy_signal_on_oversold_recovery(self):
        """RSI should signal BUY when crossing above 30 from below."""
        strategy = RSIStrategy(period=5, oversold=30.0, overbought=70.0)

        # Start with declining prices to push RSI below 30
        closes = [100.0]
        for i in range(6):
            closes.append(closes[-1] - 2.0)  # Strong decline: RSI stays at 0

        # Add recovery candles that push RSI from below 30 to above 30
        # After 6 declines: avg_gain=0, avg_loss=2, RSI=0
        # Need prev RSI < 30 and curr RSI >= 30
        # With a +3.5 change: avg_gain=(0*4+3.5)/5=0.7, avg_loss=(2*4+0)/5=1.6, RSI=30.43
        closes.append(closes[-1] + 3.5)

        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        assert result == Signal.BUY


class TestRSISellSignal:
    """Test SELL signal generation (RSI crossing below overbought)."""

    def test_sell_signal_on_overbought_reversal(self):
        """RSI should signal SELL when crossing below 70 from above."""
        strategy = RSIStrategy(period=5, oversold=30.0, overbought=70.0)

        # Start with rising prices to push RSI above 70
        closes = [100.0]
        for i in range(6):
            closes.append(closes[-1] + 2.0)  # Strong rise: RSI stays at 100

        # Add decline candle that pushes RSI from above 70 to below 70
        # After 6 rises: avg_gain=2, avg_loss=0, RSI=100
        # With a -3.5 change: avg_gain=(2*4+0)/5=1.6, avg_loss=(0*4+3.5)/5=0.7, RSI=69.57
        closes.append(closes[-1] - 3.5)

        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        assert result == Signal.SELL


class TestRSINeutralSignal:
    """Test NEUTRAL signal when no crossing occurs."""

    def test_flat_market_returns_neutral(self):
        """Flat market with no crossings should return NEUTRAL."""
        strategy = RSIStrategy(period=14)
        # All same price => no gains or losses => RSI = 50, no crossing
        candles = _make_candles_from_closes([1.0] * 20)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_already_overbought_no_crossing(self):
        """If RSI stays above 70 without crossing below, should be NEUTRAL."""
        strategy = RSIStrategy(period=5, oversold=30.0, overbought=70.0)

        # Continuously rising prices keep RSI high without crossing down
        closes = [100.0 + i * 1.0 for i in range(10)]
        candles = _make_candles_from_closes(closes)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_already_oversold_no_crossing(self):
        """If RSI stays below 30 without crossing above, should be NEUTRAL."""
        strategy = RSIStrategy(period=5, oversold=30.0, overbought=70.0)

        # Continuously falling prices keep RSI low without crossing up
        closes = [100.0 - i * 1.0 for i in range(10)]
        candles = _make_candles_from_closes(closes)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL


class TestRSIEdgeCases:
    """Edge cases for the RSI strategy."""

    def test_all_gains_rsi_is_100(self):
        """When all changes are gains, RSI should be 100."""
        strategy = RSIStrategy(period=5)
        closes = [1.0 + i * 0.01 for i in range(10)]
        candles = _make_candles_from_closes(closes)
        # RSI = 100, no crossing of oversold, so NEUTRAL
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_all_losses_rsi_near_zero(self):
        """When all changes are losses, RSI should be near 0."""
        strategy = RSIStrategy(period=5)
        closes = [2.0 - i * 0.01 for i in range(10)]
        candles = _make_candles_from_closes(closes)
        # RSI ~ 0, no crossing of overbought, so NEUTRAL
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_default_parameters_match_config(self):
        """Default parameters should match config.yaml values."""
        strategy = RSIStrategy()
        assert strategy._period == 14
        assert strategy._overbought == 70.0
        assert strategy._oversold == 30.0

    def test_custom_parameters(self):
        """Custom parameters should be stored correctly."""
        strategy = RSIStrategy(period=20, overbought=80.0, oversold=20.0)
        assert strategy._period == 20
        assert strategy._overbought == 80.0
        assert strategy._oversold == 20.0
