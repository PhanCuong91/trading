"""Unit tests for LiveTradingEngine, lot quantization, and stop level adjustments."""

from datetime import datetime
from typing import List

import pytest

from forex_signals.broker.live_runner import (
    LiveTradingEngine,
    adjust_sl_tp_for_stoplevel,
    quantize_lot_size,
)
from forex_signals.broker.mock import MockBrokerClient
from forex_signals.broker.models import Position, SymbolInfo
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import Candle, Signal, Timeframe
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies.base import Strategy


class ConstantStrategy:
    """Mock strategy returning a constant signal."""

    def __init__(self, name: str, signal: Signal, min_candles: int = 5):
        self._name = name
        self._signal = signal
        self._min_candles = min_candles

    @property
    def name(self) -> str:
        return self._name

    @property
    def min_candles(self) -> int:
        return self._min_candles

    def generate_signal(self, candles: List[Candle]) -> Signal:
        return self._signal


@pytest.fixture
def sample_spec():
    return SymbolInfo(
        name="EURUSD",
        digits=5,
        point=0.00001,
        pip_size=0.0001,
        spread_points=12,
        spread_pips=1.2,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        stop_level_points=10,  # 1 pip
        trade_contract_size=100000.0,
    )


class TestLotQuantizationAndStopLevel:
    """Tests for math helpers."""

    def test_quantize_lot_size_normal(self, sample_spec):
        assert quantize_lot_size(0.123, sample_spec) == 0.12
        assert quantize_lot_size(0.126, sample_spec) == 0.13

    def test_quantize_lot_size_clamping(self, sample_spec):
        assert quantize_lot_size(0.001, sample_spec) == 0.01
        assert quantize_lot_size(200.0, sample_spec) == 100.0

    def test_adjust_sl_tp_buy_normal(self, sample_spec):
        # Entry 1.1000, SL 1.0980 (20 pips), TP 1.1040 (40 pips), stop_level=10 pts (1 pip)
        sl, tp = adjust_sl_tp_for_stoplevel(Signal.BUY, 1.10000, 1.09800, 1.10400, sample_spec)
        assert sl == 1.09800
        assert tp == 1.10400

    def test_adjust_sl_tp_buy_violating_stoplevel(self):
        spec = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=12,
            spread_pips=1.2,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=30,  # 3 pips = 0.00030
            trade_contract_size=100000.0,
        )
        # Entry 1.10000, SL 1.09990 (only 1 pip below) -> must adjust to at least 3 pips below (1.09970)
        sl, tp = adjust_sl_tp_for_stoplevel(Signal.BUY, 1.10000, 1.09990, 1.10010, spec)
        assert sl == 1.09970
        assert tp == 1.10030

    def test_adjust_sl_tp_sell_violating_stoplevel(self):
        spec = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=12,
            spread_pips=1.2,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=20,  # 2 pips = 0.00020
            trade_contract_size=100000.0,
        )
        # Entry 1.10000, SL 1.10005 (0.5 pip above) -> adjust to 1.10020
        sl, tp = adjust_sl_tp_for_stoplevel(Signal.SELL, 1.10000, 1.10005, 1.09995, spec)
        assert sl == 1.10020
        assert tp == 1.09980


class TestLiveTradingEngine:
    """Tests for LiveTradingEngine orchestrating live signals."""

    @pytest.fixture
    def broker(self):
        b = MockBrokerClient()
        b.connect()
        # Provide sample candles
        now = datetime.now()
        candles = [
            Candle(now, 1.0850, 1.0860, 1.0840, 1.0855, 100)
            for _ in range(30)
        ]
        b.set_candles("EURUSD", candles)
        return b

    def test_step_triggers_buy_order(self, broker):
        # 5 strategies all voting BUY
        strategies = [ConstantStrategy(f"strat_{i}", Signal.BUY) for i in range(5)]
        consensus = ConsensusEngine(threshold=4)
        order_mgr = OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)

        engine = LiveTradingEngine(
            broker=broker,
            strategies=strategies,
            consensus=consensus,
            order_manager=order_mgr,
            symbol="EURUSD",
            lot_size=0.1,
            magic_number=100101,
            max_spread_pips=2.5,
        )

        res = engine.step()
        assert res is not None
        assert res.success is True
        assert res.ticket is not None

        positions = broker.get_open_positions(magic=100101)
        assert len(positions) == 1
        assert positions[0].direction == Signal.BUY

    def test_step_holds_existing_same_direction_position(self, broker):
        strategies = [ConstantStrategy(f"strat_{i}", Signal.BUY) for i in range(5)]
        consensus = ConsensusEngine(threshold=4)
        order_mgr = OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)

        engine = LiveTradingEngine(
            broker=broker,
            strategies=strategies,
            consensus=consensus,
            order_manager=order_mgr,
            symbol="EURUSD",
            lot_size=0.1,
            magic_number=100101,
        )

        # First step opens position
        res1 = engine.step()
        assert res1 is not None
        assert len(broker.get_open_positions(magic=100101)) == 1

        # Second step holds position and returns None
        res2 = engine.step()
        assert res2 is None
        assert len(broker.get_open_positions(magic=100101)) == 1

    def test_step_closes_opposite_position(self, broker):
        # First: BUY strategies open a position
        buy_strategies = [ConstantStrategy(f"strat_{i}", Signal.BUY) for i in range(5)]
        consensus = ConsensusEngine(threshold=4)
        order_mgr = OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)

        engine = LiveTradingEngine(
            broker=broker,
            strategies=buy_strategies,
            consensus=consensus,
            order_manager=order_mgr,
            symbol="EURUSD",
            lot_size=0.1,
            magic_number=100101,
        )
        engine.step()
        assert len(broker.get_open_positions(magic=100101)) == 1

        # Now consensus switches to SELL -> engine should close existing BUY position
        sell_strategies = [ConstantStrategy(f"strat_{i}", Signal.SELL) for i in range(5)]
        engine.strategies = sell_strategies

        close_res = engine.step()
        assert close_res is not None
        assert close_res.success is True
        # Open positions should now be empty
        assert len(broker.get_open_positions(magic=100101)) == 0

    def test_step_spread_filter_rejects(self, broker):
        # Set high spread on symbol
        wide_spread_spec = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=50,
            spread_pips=5.0,  # 5 pips > 2.5 max_spread_pips
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=0,
            trade_contract_size=100000.0,
        )
        broker.set_symbol_info(wide_spread_spec)

        strategies = [ConstantStrategy(f"strat_{i}", Signal.BUY) for i in range(5)]
        consensus = ConsensusEngine(threshold=4)
        order_mgr = OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)

        engine = LiveTradingEngine(
            broker=broker,
            strategies=strategies,
            consensus=consensus,
            order_manager=order_mgr,
            symbol="EURUSD",
            max_spread_pips=2.5,
        )

        res = engine.step()
        assert res is None
        assert len(broker.get_open_positions()) == 0

    def test_run_with_max_iterations(self, broker):
        strategies = [ConstantStrategy(f"strat_{i}", Signal.NEUTRAL) for i in range(5)]
        consensus = ConsensusEngine(threshold=4)
        order_mgr = OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)

        engine = LiveTradingEngine(
            broker=broker,
            strategies=strategies,
            consensus=consensus,
            order_manager=order_mgr,
            symbol="EURUSD",
            poll_interval_seconds=0.01,
        )

        engine.run(max_iterations=3)
        assert not engine._running
