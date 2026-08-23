from datetime import datetime
from typing import List

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False
    given = lambda *args, **kwargs: (lambda f: pytest.mark.skip(reason="hypothesis not installed")(f))
    settings = lambda *args, **kwargs: (lambda f: f)
    st = None


from forex_signals.broker.live_runner import (
    LiveTradingEngine,
    adjust_sl_tp_for_stoplevel,
    quantize_lot_size,
)
from forex_signals.broker.mock import MockBrokerClient
from forex_signals.broker.models import SymbolInfo
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import Candle, Signal
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies.base import Strategy


class ConstantMockStrategy:
    """Mock strategy returning a fixed signal."""

    def __init__(self, name: str, signal: Signal):
        self._name = name
        self._signal = signal

    @property
    def name(self) -> str:
        return self._name

    @property
    def min_candles(self) -> int:
        return 5

    def generate_signal(self, candles: List[Candle]) -> Signal:
        return self._signal


class TestBrokerProperties:
    """Property-based tests validating formal broker correctness properties."""

    @settings(max_examples=100)
    @given(
        entry_price=st.floats(min_value=0.5, max_value=200.0, allow_nan=False, allow_infinity=False),
        sl_distance=st.floats(min_value=0.0001, max_value=0.05, allow_nan=False, allow_infinity=False),
        tp_distance=st.floats(min_value=0.0001, max_value=0.05, allow_nan=False, allow_infinity=False),
        stop_level_pts=st.integers(min_value=0, max_value=100),
        direction=st.sampled_from([Signal.BUY, Signal.SELL]),
    )
    def test_property_11_stoplevel_compliance(
        self, entry_price: float, sl_distance: float, tp_distance: float, stop_level_pts: int, direction: Signal
    ):
        """Property 11: MT5 SL/TP distance and minimum stop level compliance.

        For any entry price, requested SL/TP, and broker stop_level_points,
        the adjusted SL and TP distance to entry SHALL be at least (stop_level_points * point).
        """
        spec = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=10,
            spread_pips=1.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=stop_level_pts,
            trade_contract_size=100000.0,
        )
        min_required_dist = stop_level_pts * spec.point

        if direction == Signal.BUY:
            raw_sl = entry_price - sl_distance
            raw_tp = entry_price + tp_distance
        else:
            raw_sl = entry_price + sl_distance
            raw_tp = entry_price - tp_distance

        adj_sl, adj_tp = adjust_sl_tp_for_stoplevel(direction, entry_price, raw_sl, raw_tp, spec)

        sl_dist = abs(entry_price - adj_sl)
        tp_dist = abs(entry_price - adj_tp)

        # Distance must be at least min_required_dist (accounting for digit rounding precision)
        eps = spec.point / 2.0
        assert sl_dist >= min_required_dist - eps
        assert tp_dist >= min_required_dist - eps

    @settings(max_examples=100)
    @given(
        raw_lot=st.floats(min_value=0.0001, max_value=500.0, allow_nan=False, allow_infinity=False),
        lot_params=st.sampled_from([(0.01, 0.01), (0.1, 0.1), (0.1, 0.01), (1.0, 0.1)]),
        max_lot=st.sampled_from([50.0, 100.0]),
    )
    def test_property_12_lot_quantization(
        self, raw_lot: float, lot_params: tuple, max_lot: float
    ):
        """Property 12: MT5 lot size quantization.

        For any requested lot size, the quantized volume SHALL be in [min_lot, max_lot]
        and (quantized - min_lot) SHALL be a multiple of lot_step.
        """
        min_lot, lot_step = lot_params

        spec = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=10,
            spread_pips=1.0,
            min_lot=min_lot,
            max_lot=max_lot,
            lot_step=lot_step,
            stop_level_points=0,
        )

        quantized = quantize_lot_size(raw_lot, spec)

        # Clamping check
        assert min_lot <= quantized <= max_lot

        # Step multiple check (modulo check with float tolerance)
        rem = (quantized - min_lot) % lot_step
        assert (rem < 1e-6) or (abs(rem - lot_step) < 1e-6)

    @settings(max_examples=50)
    @given(
        spread_pips=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        max_spread_pips=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_13_spread_filter_gatekeeping(
        self, spread_pips: float, max_spread_pips: float
    ):
        """Property 13: Spread filter order gatekeeping.

        For any live check, if live spread > max_spread_pips, NO trade order SHALL be placed.
        """
        broker = MockBrokerClient()
        broker.connect()

        spec = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=int(spread_pips * 10),
            spread_pips=spread_pips,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=0,
        )
        broker.set_symbol_info(spec)

        now = datetime.now()
        candles = [Candle(now, 1.0850, 1.0860, 1.0840, 1.0855, 100) for _ in range(20)]
        broker.set_candles("EURUSD", candles)

        strategies = [ConstantMockStrategy(f"s_{i}", Signal.BUY) for i in range(5)]
        consensus = ConsensusEngine(threshold=4)
        order_mgr = OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)

        engine = LiveTradingEngine(
            broker=broker,
            strategies=strategies,
            consensus=consensus,
            order_manager=order_mgr,
            symbol="EURUSD",
            max_spread_pips=max_spread_pips,
        )

        res = engine.step()

        if spread_pips > max_spread_pips:
            assert res is None
            assert len(broker.get_open_positions()) == 0
        else:
            assert res is not None
            assert res.success is True

    @settings(max_examples=50)
    @given(
        bot_magic=st.integers(min_value=100001, max_value=999999),
        other_magic=st.integers(min_value=100001, max_value=999999),
    )
    def test_property_14_bot_magic_number_isolation(
        self, bot_magic: int, other_magic: int
    ):
        """Property 14: Order ticket tracking and bot isolation.

        Orders dispatched with magic M are correctly isolated and queried by magic M.
        """
        broker = MockBrokerClient()
        broker.connect()

        # Place bot order
        res1 = broker.place_order("EURUSD", Signal.BUY, 0.1, 1.0800, 1.0900, magic=bot_magic)

        # Place other order if different magic
        if bot_magic != other_magic:
            broker.place_order("EURUSD", Signal.SELL, 0.2, 1.0900, 1.0700, magic=other_magic)

        bot_positions = broker.get_open_positions(magic=bot_magic)
        assert len(bot_positions) == 1
        assert bot_positions[0].ticket == res1.ticket
        assert bot_positions[0].magic == bot_magic
