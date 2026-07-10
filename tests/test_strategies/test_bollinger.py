"""Tests for the Bollinger Bands strategy."""

import math
from datetime import datetime, timedelta
from typing import List, Optional

import pytest

from forex_signals.data.models import Candle, Signal
from forex_signals.strategies.base import Strategy
from forex_signals.strategies.bollinger import BollingerBandsStrategy


def _make_candle(
    close: float,
    index: int = 0,
    high: Optional[float] = None,
    low: Optional[float] = None,
    base_time: datetime = datetime(2024, 1, 1),
) -> Candle:
    return Candle(
        timestamp=base_time + timedelta(minutes=5 * index),
        open=close,
        high=high if high is not None else close + 0.01,
        low=low if low is not None else close - 0.01,
        close=close,
        volume=100.0,
    )


def _make_candles_from_closes(closes: List[float]) -> List[Candle]:
    """Create candles from a list of close prices with default high/low."""
    return [_make_candle(close=c, index=i) for i, c in enumerate(closes)]


class TestBollingerBandsProtocol:
    """Test that BollingerBandsStrategy conforms to Strategy protocol."""

    def test_conforms_to_strategy_protocol(self):
        strategy: Strategy = BollingerBandsStrategy()
        assert strategy.name == "Bollinger Bands"
        assert strategy.min_candles > 0

    def test_name_property(self):
        strategy = BollingerBandsStrategy()
        assert strategy.name == "Bollinger Bands"

    def test_min_candles_default(self):
        strategy = BollingerBandsStrategy()
        # period(20) + 1 = 21
        assert strategy.min_candles == 21

    def test_min_candles_custom(self):
        strategy = BollingerBandsStrategy(period=10, std_dev=1.5)
        # 10 + 1 = 11
        assert strategy.min_candles == 11


class TestBollingerBandsInsufficientData:
    """Test NEUTRAL signal when insufficient candles."""

    def test_empty_candles(self):
        strategy = BollingerBandsStrategy()
        assert strategy.generate_signal([]) == Signal.NEUTRAL

    def test_fewer_than_min_candles(self):
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)
        candles = _make_candles_from_closes([1.0] * 5)  # need 6
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_exactly_one_less_than_min(self):
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)
        candles = _make_candles_from_closes([1.0] * 5)  # min is 6
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_exactly_min_candles_returns_signal(self):
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)
        candles = _make_candles_from_closes([1.0] * 6)  # exactly min_candles
        # Flat market with default high/low should be NEUTRAL
        assert strategy.generate_signal(candles) == Signal.NEUTRAL


class TestBollingerBandsBuySignal:
    """Test BUY signal generation (lower band reversal)."""

    def test_buy_on_lower_band_reversal(self):
        """
        Previous candle's low touches/crosses below lower band,
        current candle closes above lower band = BUY.
        """
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)

        # Create 6 candles (period=5, need 5+1=6)
        # First 4 candles at 1.0, then a dip and recovery
        # The window for bands is the last 5 candles
        # Mean = average of last 5 closes
        # We need prev candle's low <= lower_band and curr candle's close > lower_band

        # Build candles: 4 at 1.0, prev dips low, current recovers
        closes = [1.0, 1.0, 1.0, 1.0, 0.95, 1.0]

        # Window (last 5): [1.0, 1.0, 1.0, 0.95, 1.0]
        # mean = (1.0+1.0+1.0+0.95+1.0)/5 = 4.95/5 = 0.99
        # variance = ((0.01)^2 + (0.01)^2 + (0.01)^2 + (-0.04)^2 + (0.01)^2) / 5
        #          = (0.0001+0.0001+0.0001+0.0016+0.0001)/5 = 0.002/5 = 0.0004
        # std = sqrt(0.0004) = 0.02
        # lower_band = 0.99 - 2*0.02 = 0.95
        # prev candle (index 4): close=0.95, low=0.95-0.01=0.94
        # 0.94 <= 0.95 ✓ (low touches below lower band)
        # curr candle (index 5): close=1.0
        # 1.0 > 0.95 ✓ (close above lower band)

        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        assert result == Signal.BUY

    def test_buy_with_explicit_low_crossing_band(self):
        """Explicit low that crosses well below the lower band."""
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)

        # All closes at 1.0 for simple band calculation
        # Window (last 5): all 1.0 → mean=1.0, std=0, lower_band=1.0
        # With zero std, lower_band = mean = 1.0
        # prev candle low must be <= 1.0
        # curr candle close must be > 1.0

        # Use candles where the window has some variance
        base_candles = [
            _make_candle(close=1.0, index=0),
            _make_candle(close=1.02, index=1),
            _make_candle(close=0.98, index=2),
            _make_candle(close=1.01, index=3),
            # Previous candle: close at 0.99, but low dips far
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=20),
                open=1.0,
                high=1.0,
                low=0.90,  # very low
                close=0.99,
                volume=100.0,
            ),
            # Current candle: recovers
            _make_candle(close=1.01, index=5),
        ]

        # Window (last 5): closes = [1.02, 0.98, 1.01, 0.99, 1.01]
        # mean = (1.02+0.98+1.01+0.99+1.01)/5 = 5.01/5 = 1.002
        # deviations: [0.018, -0.022, 0.008, -0.012, 0.008]
        # variance = (0.018^2+0.022^2+0.008^2+0.012^2+0.008^2)/5
        #          = (0.000324+0.000484+0.000064+0.000144+0.000064)/5
        #          = 0.00108/5 = 0.000216
        # std = sqrt(0.000216) ≈ 0.0147
        # lower_band = 1.002 - 2*0.0147 ≈ 0.9726
        # prev low = 0.90 <= 0.9726 ✓
        # curr close = 1.01 > 0.9726 ✓

        result = strategy.generate_signal(base_candles)
        assert result == Signal.BUY


class TestBollingerBandsSellSignal:
    """Test SELL signal generation (upper band reversal)."""

    def test_sell_on_upper_band_reversal(self):
        """
        Previous candle's high touches/crosses above upper band,
        current candle closes below upper band = SELL.
        """
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)

        # Build candles: 4 at 1.0, prev spikes high, current drops back
        closes = [1.0, 1.0, 1.0, 1.0, 1.05, 1.0]

        # Window (last 5): [1.0, 1.0, 1.0, 1.05, 1.0]
        # mean = (1.0+1.0+1.0+1.05+1.0)/5 = 5.05/5 = 1.01
        # variance = ((-0.01)^2+(-0.01)^2+(-0.01)^2+(0.04)^2+(-0.01)^2)/5
        #          = (0.0001+0.0001+0.0001+0.0016+0.0001)/5 = 0.002/5 = 0.0004
        # std = sqrt(0.0004) = 0.02
        # upper_band = 1.01 + 2*0.02 = 1.05
        # prev candle (index 4): close=1.05, high=1.05+0.01=1.06
        # 1.06 >= 1.05 ✓ (high touches above upper band)
        # curr candle (index 5): close=1.0
        # 1.0 < 1.05 ✓ (close below upper band)

        candles = _make_candles_from_closes(closes)
        result = strategy.generate_signal(candles)
        assert result == Signal.SELL

    def test_sell_with_explicit_high_crossing_band(self):
        """Explicit high that crosses well above the upper band."""
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)

        base_candles = [
            _make_candle(close=1.0, index=0),
            _make_candle(close=0.98, index=1),
            _make_candle(close=1.02, index=2),
            _make_candle(close=0.99, index=3),
            # Previous candle: close at 1.01, but high spikes far
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=20),
                open=1.0,
                high=1.10,  # very high
                low=1.0,
                close=1.01,
                volume=100.0,
            ),
            # Current candle: drops back
            _make_candle(close=0.99, index=5),
        ]

        # Window (last 5): closes = [0.98, 1.02, 0.99, 1.01, 0.99]
        # mean = (0.98+1.02+0.99+1.01+0.99)/5 = 4.99/5 = 0.998
        # deviations: [-0.018, 0.022, -0.008, 0.012, -0.008]
        # variance = (0.000324+0.000484+0.000064+0.000144+0.000064)/5
        #          = 0.00108/5 = 0.000216
        # std ≈ 0.0147
        # upper_band = 0.998 + 2*0.0147 ≈ 1.0274
        # prev high = 1.10 >= 1.0274 ✓
        # curr close = 0.99 < 1.0274 ✓

        result = strategy.generate_signal(base_candles)
        assert result == Signal.SELL


class TestBollingerBandsNeutralSignal:
    """Test NEUTRAL signal when no band reversal occurs."""

    def test_flat_market_returns_neutral(self):
        """Flat market within bands should return NEUTRAL."""
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)
        candles = _make_candles_from_closes([1.0] * 6)
        # All closes identical → std=0, bands collapse to mean
        # prev low = 0.99, lower_band = 1.0 → 0.99 <= 1.0 ✓
        # curr close = 1.0, lower_band = 1.0 → 1.0 > 1.0? No!
        # So this is NEUTRAL because curr close is not > lower_band
        assert strategy.generate_signal(candles) == Signal.NEUTRAL

    def test_price_within_bands_no_touch(self):
        """Price staying well within bands should return NEUTRAL."""
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)

        # Create candles with enough spread for wide bands,
        # but prev candle doesn't touch either band
        candles = [
            _make_candle(close=1.0, index=0),
            _make_candle(close=1.1, index=1),
            _make_candle(close=0.9, index=2),
            _make_candle(close=1.1, index=3),
            # Previous candle: stays in middle with no extreme high/low
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=20),
                open=1.0,
                high=1.02,
                low=0.98,
                close=1.0,
                volume=100.0,
            ),
            # Current candle: also in the middle
            _make_candle(close=1.0, index=5),
        ]

        # Window (last 5): closes = [1.1, 0.9, 1.1, 1.0, 1.0]
        # mean = (1.1+0.9+1.1+1.0+1.0)/5 = 5.1/5 = 1.02
        # std will be substantial, so bands are wide
        # prev high=1.02, prev low=0.98 — should be within bands
        result = strategy.generate_signal(candles)
        assert result == Signal.NEUTRAL

    def test_low_touches_lower_band_but_no_reversal(self):
        """Prev low touches lower band but current candle doesn't close above it."""
        strategy = BollingerBandsStrategy(period=5, std_dev=2.0)

        # Same setup as BUY test but current candle also closes below lower band
        closes = [1.0, 1.0, 1.0, 1.0, 0.95, 0.94]

        # Window (last 5): [1.0, 1.0, 1.0, 0.95, 0.94]
        # mean = (1.0+1.0+1.0+0.95+0.94)/5 = 4.89/5 = 0.978
        # deviations: [0.022, 0.022, 0.022, -0.028, -0.038]
        # variance = (0.000484+0.000484+0.000484+0.000784+0.001444)/5
        #          = 0.00368/5 = 0.000736
        # std = sqrt(0.000736) ≈ 0.02713
        # lower_band = 0.978 - 2*0.02713 ≈ 0.9237
        # prev low = 0.95 - 0.01 = 0.94 > 0.9237? Yes!
        # prev low doesn't touch lower band, so NEUTRAL
        # Actually let's verify - we need a case where prev low touches but no reversal
        # Use a larger dip to ensure prev touches the band

        # Better approach: use period=3 for simpler calculation
        strategy3 = BollingerBandsStrategy(period=3, std_dev=2.0)
        # Need 4 candles (period+1)
        # Window (last 3): [close[1], close[2], close[3]]
        # Make window have big spread, prev low touches lower, but curr stays below

        candles = [
            _make_candle(close=1.1, index=0),
            _make_candle(close=1.0, index=1),
            _make_candle(close=1.1, index=2),
            # prev candle (index 2): close=1.1, high=1.11, low=1.09
            # curr candle (index 3):
        ]

        # Let me make it simpler with explicit candles
        candles = [
            _make_candle(close=1.0, index=0),
            _make_candle(close=1.1, index=1),
            # Previous candle with low that will touch lower band
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=10),
                open=0.9,
                high=0.95,
                low=0.80,  # very low
                close=0.9,
                volume=100.0,
            ),
            # Current candle: stays low (no reversal above lower band)
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=15),
                open=0.85,
                high=0.86,
                low=0.84,
                close=0.85,
                volume=100.0,
            ),
        ]

        # Window (last 3): closes = [1.1, 0.9, 0.85]
        # mean = (1.1+0.9+0.85)/3 = 2.85/3 = 0.95
        # variance = ((0.15)^2+(-0.05)^2+(-0.1)^2)/3 = (0.0225+0.0025+0.01)/3 = 0.035/3 ≈ 0.01167
        # std ≈ 0.108
        # lower_band = 0.95 - 2*0.108 = 0.734
        # prev low = 0.80 > 0.734? Yes, so prev doesn't touch lower band!
        # Need even lower or tighter bands

        # Use period=3 with std_dev=1.0 for tighter bands
        strategy_tight = BollingerBandsStrategy(period=3, std_dev=1.0)
        # lower_band = 0.95 - 1*0.108 = 0.842
        # prev low = 0.80 <= 0.842 ✓
        # curr close = 0.85 > 0.842 ✓ → This would be BUY!
        # We need curr close <= lower_band for NEUTRAL
        # curr close = 0.84 → still > 0.842? Barely.
        # Let's set curr close very low

        candles_neutral = [
            _make_candle(close=1.0, index=0),
            _make_candle(close=1.1, index=1),
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=10),
                open=0.9,
                high=0.95,
                low=0.80,
                close=0.9,
                volume=100.0,
            ),
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=15),
                open=0.80,
                high=0.81,
                low=0.79,
                close=0.80,  # closes below lower band
                volume=100.0,
            ),
        ]

        # Window (last 3): closes = [1.1, 0.9, 0.80]
        # mean = (1.1+0.9+0.80)/3 = 2.8/3 ≈ 0.9333
        # variance = ((0.1667)^2+(-0.0333)^2+(-0.1333)^2)/3
        #          = (0.0278+0.00111+0.01778)/3 ≈ 0.04669/3 ≈ 0.01556
        # std ≈ 0.1247
        # lower_band = 0.9333 - 1.0*0.1247 ≈ 0.8086
        # prev low = 0.80 <= 0.8086 ✓
        # curr close = 0.80 > 0.8086? No! 0.80 < 0.8086 → NEUTRAL ✓

        result = strategy_tight.generate_signal(candles_neutral)
        assert result == Signal.NEUTRAL


class TestBollingerBandsParameters:
    """Test parameter configuration."""

    def test_default_parameters(self):
        strategy = BollingerBandsStrategy()
        assert strategy._period == 20
        assert strategy._std_dev == 2.0

    def test_custom_parameters(self):
        strategy = BollingerBandsStrategy(period=10, std_dev=1.5)
        assert strategy._period == 10
        assert strategy._std_dev == 1.5


class TestBollingerBandsMath:
    """Test internal band calculations."""

    def test_sma_calculation(self):
        """Verify SMA is calculated correctly."""
        candles = _make_candles_from_closes([1.0, 2.0, 3.0, 4.0, 5.0])
        mean = BollingerBandsStrategy._sma(candles)
        assert mean == pytest.approx(3.0)

    def test_population_std_calculation(self):
        """Verify population standard deviation is correct."""
        candles = _make_candles_from_closes([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        mean = BollingerBandsStrategy._sma(candles)
        std = BollingerBandsStrategy._population_std(candles, mean)
        # Known population std for [2,4,4,4,5,5,7,9] = 2.0
        assert std == pytest.approx(2.0)

    def test_zero_std_for_flat_data(self):
        """All same values should produce zero standard deviation."""
        candles = _make_candles_from_closes([1.5] * 10)
        mean = BollingerBandsStrategy._sma(candles)
        std = BollingerBandsStrategy._population_std(candles, mean)
        assert std == pytest.approx(0.0)
