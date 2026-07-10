"""Tests for the MACD strategy."""

from datetime import datetime, timedelta
from typing import List

import pytest

from forex_signals.data.models import Candle, Signal
from forex_signals.strategies.base import Strategy
from forex_signals.strategies.macd import MACDStrategy


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


class TestMACDStrategyProtocol:
    """Test that MACDStrategy conforms to Strategy protocol."""

    def test_conforms_to_strategy_protocol(self):
        strategy: Strategy = MACDStrategy()
        assert strategy.name == "MACD"
        assert strategy.min_candles > 0

    def test_name_property(self):
        strategy = MACDStrategy()
        assert strategy.name == "MACD"

    def test_min_candles_default(self):
        strategy = MACDStrategy()
        # slow_period + signal_period = 26 + 9 = 35
        assert strategy.min_candles == 35

    def test_min_candles_custom(self):
        strategy = MACDStrategy(fast_period=8, slow_period=21, signal_period=5)
        # 21 + 5 = 26
        assert strategy.min_candles == 26


class TestMACDInsufficientData:
    """Test NEUTRAL signal when insufficient candles."""

    def test_empty_candles(self):
        strategy = MACDStrategy()
        assert strategy.generate_signal([]) == Signal.NEUTRAL

    def test_fewer_than_min_candles(self):
        strategy = MACDStrategy()
        candles = _make_candles_from_closes([1.0] * 34)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_exactly_min_candles_returns_valid_signal(self):
        strategy = MACDStrategy()
        candles = _make_candles_from_closes([1.0] * 35)
        result = strategy.generate_signal(candles)
        assert result in (Signal.BUY, Signal.SELL, Signal.NEUTRAL)


class TestMACDBuySignal:
    """Test BUY signal generation (MACD crossing above signal line)."""

    def test_buy_signal_on_upward_crossover(self):
        """MACD should signal BUY when MACD line crosses above signal line."""
        strategy = MACDStrategy()

        # 40-candle downtrend establishes negative MACD below signal line
        closes: List[float] = []
        for i in range(40):
            closes.append(1.30 - i * 0.003)

        # 2 recovery candles cause MACD to cross above signal on the last bar
        for i in range(2):
            closes.append(closes[-1] + 0.004)

        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        assert result == Signal.BUY


class TestMACDSellSignal:
    """Test SELL signal generation (MACD crossing below signal line)."""

    def test_sell_signal_on_downward_crossover(self):
        """MACD should signal SELL when MACD line crosses below signal line."""
        strategy = MACDStrategy()

        # 40-candle uptrend establishes positive MACD above signal line
        closes: List[float] = []
        for i in range(40):
            closes.append(1.10 + i * 0.003)

        # 2 decline candles cause MACD to cross below signal on the last bar
        for i in range(2):
            closes.append(closes[-1] - 0.004)

        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        assert result == Signal.SELL


class TestMACDNeutralSignal:
    """Test NEUTRAL signal when no crossing occurs."""

    def test_flat_market_returns_neutral(self):
        """Flat market with no crossings should return NEUTRAL."""
        strategy = MACDStrategy()
        candles = _make_candles_from_closes([1.0] * 40)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_steady_uptrend_no_crossing(self):
        """Steady uptrend without reversal should stay NEUTRAL (no crossover)."""
        strategy = MACDStrategy()
        # Very gradual consistent uptrend — MACD stays above signal, no crossing
        closes = [1.0 + i * 0.0001 for i in range(50)]
        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        # In a steady trend, MACD should be above signal consistently → NEUTRAL
        assert result == Signal.NEUTRAL


class TestMACDEdgeCases:
    """Edge cases for the MACD strategy."""

    def test_default_parameters_match_config(self):
        """Default parameters should match config.yaml values (12, 26, 9)."""
        strategy = MACDStrategy()
        assert strategy._fast_period == 12
        assert strategy._slow_period == 26
        assert strategy._signal_period == 9

    def test_custom_parameters(self):
        """Custom parameters should be stored correctly."""
        strategy = MACDStrategy(fast_period=8, slow_period=21, signal_period=5)
        assert strategy._fast_period == 8
        assert strategy._slow_period == 21
        assert strategy._signal_period == 5

    def test_all_same_price_returns_neutral(self):
        """When all candles have the same close, MACD and signal are both 0."""
        strategy = MACDStrategy()
        candles = _make_candles_from_closes([1.5] * 40)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL
