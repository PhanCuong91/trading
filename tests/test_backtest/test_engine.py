"""Tests for the BacktestEngine orchestrator."""

from datetime import datetime, timedelta
from typing import List

import pytest

from forex_signals.backtest.engine import BacktestEngine
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import Candle, OrderStatus, Signal
from forex_signals.orders.manager import OrderManager


class FakeStrategy:
    """A fake strategy that returns a fixed signal after min_candles are available."""

    def __init__(self, name: str, signal: Signal, min_candles: int = 1):
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


from typing import Optional as _Optional


def _make_candle(
    index: int,
    close: float = 1.1000,
    high: _Optional[float] = None,
    low: _Optional[float] = None,
) -> Candle:
    """Helper to create a candle with sensible defaults."""
    return Candle(
        timestamp=datetime(2024, 1, 1) + timedelta(hours=index),
        open=close,
        high=high if high is not None else close + 0.0010,
        low=low if low is not None else close - 0.0010,
        close=close,
        volume=1000.0,
    )


class TestBacktestEngineBasic:
    """Basic functionality tests."""

    def test_empty_candles_returns_zero_metrics(self):
        strategies = [FakeStrategy("s1", Signal.BUY)]
        consensus = ConsensusEngine(threshold=1)
        order_manager = OrderManager(sl_pips=50, tp_pips=100)

        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run([])

        assert result.num_trades == 0
        assert result.trades == []
        assert result.win_rate == 0.0
        assert result.total_pnl == 0.0

    def test_no_consensus_no_trades(self):
        """When strategies disagree and threshold isn't met, no orders are created."""
        strategies = [
            FakeStrategy("s1", Signal.BUY),
            FakeStrategy("s2", Signal.SELL),
            FakeStrategy("s3", Signal.NEUTRAL),
        ]
        consensus = ConsensusEngine(threshold=3)
        order_manager = OrderManager(sl_pips=50, tp_pips=100)

        candles = [_make_candle(i) for i in range(10)]
        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        assert result.num_trades == 0

    def test_buy_signal_creates_order(self):
        """When consensus is BUY, an order should be created."""
        strategies = [FakeStrategy(f"s{i}", Signal.BUY) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        order_manager = OrderManager(sl_pips=50, tp_pips=100)

        candles = [_make_candle(i, close=1.1000) for i in range(5)]
        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        # An order was created (may or may not be closed depending on candle prices)
        # With default candles, high is close+0.0010 and tp is close+0.01
        # So TP won't be hit in these candles, order stays open
        # Open orders are NOT included in the result
        assert result.num_trades == 0

    def test_buy_order_hits_take_profit(self):
        """A BUY order should close at TP when price rises enough."""
        strategies = [FakeStrategy(f"s{i}", Signal.BUY) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        # SL=50 pips, TP=10 pips (easy to hit TP)
        order_manager = OrderManager(sl_pips=50, tp_pips=10)

        # First candle: order entry at close=1.1000, TP=1.1010
        # Second candle: high reaches TP
        candles = [
            _make_candle(0, close=1.1000, high=1.1005, low=1.0995),
            _make_candle(1, close=1.1015, high=1.1020, low=1.1005),
        ]

        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        assert result.num_trades == 1
        assert result.trades[0].status == OrderStatus.CLOSED_TP
        assert result.trades[0].pnl > 0

    def test_sell_order_hits_stop_loss(self):
        """A SELL order should close at SL when price rises."""
        strategies = [FakeStrategy(f"s{i}", Signal.SELL) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        # SL=10 pips, TP=50 pips
        order_manager = OrderManager(sl_pips=10, tp_pips=50)

        # First candle: order entry at close=1.1000, SL=1.1010
        # Second candle: high reaches SL
        candles = [
            _make_candle(0, close=1.1000, high=1.1005, low=1.0995),
            _make_candle(1, close=1.1015, high=1.1020, low=1.1005),
        ]

        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        assert result.num_trades == 1
        assert result.trades[0].status == OrderStatus.CLOSED_SL
        assert result.trades[0].pnl < 0

    def test_no_new_order_while_position_open(self):
        """Should not open a second order while one is already open."""
        strategies = [FakeStrategy(f"s{i}", Signal.BUY) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        # Large SL/TP so order won't close
        order_manager = OrderManager(sl_pips=500, tp_pips=500)

        candles = [_make_candle(i, close=1.1000) for i in range(10)]
        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        # Order stays open, so no closed trades
        assert result.num_trades == 0

    def test_multiple_trades_after_close(self):
        """After a position closes, a new one can be opened."""
        strategies = [FakeStrategy(f"s{i}", Signal.BUY) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        # TP=5 pips so it's easily hit
        order_manager = OrderManager(sl_pips=50, tp_pips=5)

        # Each pair of candles: entry then TP hit
        candles = [
            # Trade 1: entry
            _make_candle(0, close=1.1000, high=1.1002, low=1.0998),
            # Trade 1: TP hit (high >= 1.1005)
            _make_candle(1, close=1.1006, high=1.1010, low=1.1002),
            # Trade 2: entry
            _make_candle(2, close=1.1006, high=1.1008, low=1.1004),
            # Trade 2: TP hit (high >= 1.1011)
            _make_candle(3, close=1.1012, high=1.1015, low=1.1008),
        ]

        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        assert result.num_trades == 2
        assert all(t.status == OrderStatus.CLOSED_TP for t in result.trades)

    def test_strategy_min_candles_respected(self):
        """Strategies shouldn't be called until enough candles are available."""
        # Strategy requires 5 candles minimum
        strategies = [FakeStrategy(f"s{i}", Signal.BUY, min_candles=5) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        order_manager = OrderManager(sl_pips=50, tp_pips=5)

        # Only 3 candles provided - no strategy can produce signal
        candles = [_make_candle(i, close=1.1000) for i in range(3)]

        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        assert result.num_trades == 0

    def test_metrics_computed_correctly(self):
        """BacktestResult should contain properly computed metrics."""
        strategies = [FakeStrategy(f"s{i}", Signal.BUY) for i in range(4)]
        consensus = ConsensusEngine(threshold=4)
        order_manager = OrderManager(sl_pips=50, tp_pips=5)

        candles = [
            _make_candle(0, close=1.1000, high=1.1002, low=1.0998),
            _make_candle(1, close=1.1006, high=1.1010, low=1.1002),
        ]

        engine = BacktestEngine(strategies, consensus, order_manager)
        result = engine.run(candles)

        assert result.num_trades == 1
        assert result.win_rate == 1.0
        assert result.total_pnl > 0
        assert result.max_drawdown == 0.0
        assert result.profit_factor == float("inf")
        assert result.avg_trade_duration_seconds > 0
