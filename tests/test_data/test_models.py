"""Verification script for data models."""

from datetime import datetime
from forex_signals.data.models import (
    Timeframe, Signal, OrderStatus,
    Candle, StrategySignal, Order,
    BacktestConfig, BacktestResult,
)


def test_enums():
    assert Timeframe.M5.value == "5m"
    assert Timeframe.M15.value == "15m"
    assert Timeframe.H1.value == "1h"
    assert Timeframe.H4.value == "4h"
    assert Timeframe.D1.value == "1d"

    assert Signal.BUY.value == "BUY"
    assert Signal.SELL.value == "SELL"
    assert Signal.NEUTRAL.value == "NEUTRAL"

    assert OrderStatus.OPEN.value == "OPEN"
    assert OrderStatus.CLOSED_TP.value == "CLOSED_TP"
    assert OrderStatus.CLOSED_SL.value == "CLOSED_SL"


def test_candle_frozen():
    c = Candle(
        timestamp=datetime(2024, 1, 1),
        open=1.1000,
        high=1.1050,
        low=1.0950,
        close=1.1020,
        volume=1000.0,
    )
    assert c.open == 1.1000
    assert c.high == 1.1050
    try:
        c.open = 2.0  # type: ignore
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass  # Expected - frozen dataclass


def test_strategy_signal_frozen():
    ss = StrategySignal(
        strategy_name="RSI",
        signal=Signal.BUY,
        timestamp=datetime(2024, 1, 1),
    )
    assert ss.strategy_name == "RSI"
    assert ss.signal == Signal.BUY


def test_order_mutable():
    o = Order(
        direction=Signal.BUY,
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.1040,
        entry_time=datetime(2024, 1, 1),
    )
    assert o.status == OrderStatus.OPEN
    assert o.exit_time is None
    assert o.exit_price is None
    assert o.pnl is None

    # Order should be mutable for lifecycle updates
    o.status = OrderStatus.CLOSED_TP
    o.exit_time = datetime(2024, 1, 2)
    o.exit_price = 1.1040
    o.pnl = 0.0040
    assert o.status == OrderStatus.CLOSED_TP


def test_backtest_config_frozen():
    bc = BacktestConfig(
        pair="EURUSD=X",
        timeframe=Timeframe.M5,
        sl_pips=20.0,
        tp_pips=40.0,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
    )
    assert bc.pair == "EURUSD=X"
    assert bc.timeframe == Timeframe.M5


def test_backtest_result_frozen():
    br = BacktestResult(
        trades=[],
        win_rate=0.55,
        total_pnl=150.0,
        max_drawdown=25.0,
        sharpe_ratio=1.2,
        profit_factor=1.8,
        avg_trade_duration_seconds=3600.0,
        num_trades=100,
    )
    assert br.win_rate == 0.55
    assert br.num_trades == 100
