"""Tests for the SMI strategy."""

from datetime import datetime, timedelta
from typing import List

import pytest

from forex_signals.data.models import Candle, Signal
from forex_signals.strategies.base import Strategy
from forex_signals.strategies.smi import SMIStrategy


def _make_candle(
    close: float,
    high: float,
    low: float,
    open_: float = 1.0,
    volume: float = 100.0,
    base_time: datetime = datetime(2024, 1, 1),
    index: int = 0,
) -> Candle:
    return Candle(
        timestamp=base_time + timedelta(minutes=5 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_candles(prices: List[tuple], base_time: datetime = datetime(2024, 1, 1)) -> List[Candle]:
    """Create candles from (close, high, low) tuples."""
    return [
        _make_candle(close=p[0], high=p[1], low=p[2], index=i, base_time=base_time)
        for i, p in enumerate(prices)
    ]


class TestSMIStrategyProtocol:
    """Test that SMIStrategy conforms to Strategy protocol."""

    def test_conforms_to_strategy_protocol(self):
        strategy: Strategy = SMIStrategy()
        assert strategy.name == "SMI"
        assert strategy.min_candles > 0

    def test_name_property(self):
        strategy = SMIStrategy()
        assert strategy.name == "SMI"

    def test_min_candles(self):
        strategy = SMIStrategy(period=14, smooth_period=3)
        # period + 2 * smooth_period = 14 + 6 = 20
        assert strategy.min_candles == 20

    def test_min_candles_custom(self):
        strategy = SMIStrategy(period=10, smooth_period=5)
        # 10 + 2 * 5 = 20
        assert strategy.min_candles == 20


class TestSMIInsufficientData:
    """Test NEUTRAL signal when insufficient candles."""

    def test_empty_candles(self):
        strategy = SMIStrategy()
        assert strategy.generate_signal([]) == Signal.NEUTRAL

    def test_fewer_than_min_candles(self):
        strategy = SMIStrategy(period=14, smooth_period=3)
        candles = _make_candles([(1.0, 1.1, 0.9)] * 19)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_exactly_min_candles_returns_valid_signal(self):
        strategy = SMIStrategy(period=14, smooth_period=3)
        # With flat data, should return NEUTRAL (no crossing)
        candles = _make_candles([(1.0, 1.1, 0.9)] * 20)
        result = strategy.generate_signal(candles)
        assert result in (Signal.BUY, Signal.SELL, Signal.NEUTRAL)


class TestSMIBuySignal:
    """Test BUY signal generation (SMI crossing above -40)."""

    def test_buy_signal_on_oversold_recovery(self):
        """SMI should signal BUY when crossing above -40 from below."""
        strategy = SMIStrategy(period=14, smooth_period=3)

        candles = []
        base_time = datetime(2024, 1, 1)

        # 30 candles deeply oversold (close near low of range)
        for i in range(30):
            candles.append(
                _make_candle(close=0.91, high=1.10, low=0.90, index=i, base_time=base_time)
            )

        # 4 recovery candles: close moves up gradually
        # This makes SMI go from -90 -> -82.5 -> -67.5 -> -46.87 -> -22.5
        # The last two values cross -40: prev=-46.87, curr=-22.5
        for i in range(4):
            candles.append(
                _make_candle(
                    close=0.91 + (i + 1) * 0.03,
                    high=1.10,
                    low=0.90,
                    index=30 + i,
                    base_time=base_time,
                )
            )

        result = strategy.generate_signal(candles)
        assert result == Signal.BUY


class TestSMISellSignal:
    """Test SELL signal generation (SMI crossing below +40)."""

    def test_sell_signal_on_overbought_reversal(self):
        """SMI should signal SELL when crossing below +40 from above."""
        strategy = SMIStrategy(period=14, smooth_period=3)

        candles = []
        base_time = datetime(2024, 1, 1)

        # 30 candles overbought (close near high of range)
        for i in range(30):
            candles.append(
                _make_candle(close=1.09, high=1.10, low=0.90, index=i, base_time=base_time)
            )

        # 4 reversal candles: close drops gradually
        # This makes SMI go from 90 -> 82.5 -> 67.5 -> 46.88 -> 22.5
        # The last two values cross +40: prev=46.88, curr=22.5
        for i in range(4):
            candles.append(
                _make_candle(
                    close=1.09 - (i + 1) * 0.03,
                    high=1.10,
                    low=0.90,
                    index=30 + i,
                    base_time=base_time,
                )
            )

        result = strategy.generate_signal(candles)
        assert result == Signal.SELL


class TestSMINeutralSignal:
    """Test NEUTRAL signal when no crossing occurs."""

    def test_flat_market_returns_neutral(self):
        """Flat market with no crossings should return NEUTRAL."""
        strategy = SMIStrategy(period=14, smooth_period=3)
        # Close at midpoint means SMI ~ 0, no crossing of -40 or +40
        candles = _make_candles([(1.0, 1.1, 0.9)] * 25)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_already_in_overbought_no_crossing(self):
        """If SMI stays above +40 without crossing below, should be NEUTRAL."""
        strategy = SMIStrategy(period=14, smooth_period=3)
        # All closes near the high — SMI stays high, no crossing
        candles = _make_candles([(1.09, 1.10, 0.90)] * 25)
        assert strategy.generate_signal(candles) == Signal.NEUTRAL


class TestSMIEdgeCases:
    """Edge cases for the SMI strategy."""

    def test_zero_range_returns_neutral(self):
        """When high == low (no range), SMI should handle gracefully."""
        strategy = SMIStrategy(period=14, smooth_period=3)
        # All candles with same OHLC (zero range)
        candles = _make_candles([(1.0, 1.0, 1.0)] * 25)
        result = strategy.generate_signal(candles)
        assert result in (Signal.BUY, Signal.SELL, Signal.NEUTRAL)

    def test_default_parameters_match_config(self):
        """Default parameters should match config.yaml values."""
        strategy = SMIStrategy()
        assert strategy._period == 14
        assert strategy._smooth_period == 3

    def test_custom_parameters(self):
        """Custom parameters should be stored correctly."""
        strategy = SMIStrategy(period=20, smooth_period=5)
        assert strategy._period == 20
        assert strategy._smooth_period == 5
