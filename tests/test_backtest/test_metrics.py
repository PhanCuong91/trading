"""Unit tests for MetricsCalculator."""

import math
from datetime import datetime, timedelta

import pytest

from forex_signals.backtest.metrics import MetricsCalculator
from forex_signals.data.models import Order, OrderStatus, Signal


def _make_trade(pnl, duration_seconds=None):
    """Helper to create a closed trade with a given pnl."""
    entry_time = datetime(2024, 1, 1, 12, 0, 0)
    exit_time = (
        entry_time + timedelta(seconds=duration_seconds)
        if duration_seconds is not None
        else None
    )
    return Order(
        direction=Signal.BUY,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1050,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_price=1.1050 if pnl > 0 else 1.0950,
        status=OrderStatus.CLOSED_TP if pnl > 0 else OrderStatus.CLOSED_SL,
        pnl=pnl,
    )


class TestWinRate:
    def test_empty_trades(self):
        assert MetricsCalculator.win_rate([]) == 0.0

    def test_all_winners(self):
        trades = [_make_trade(10.0), _make_trade(20.0), _make_trade(5.0)]
        assert MetricsCalculator.win_rate(trades) == 1.0

    def test_all_losers(self):
        trades = [_make_trade(-10.0), _make_trade(-20.0)]
        assert MetricsCalculator.win_rate(trades) == 0.0

    def test_mixed(self):
        trades = [_make_trade(10.0), _make_trade(-5.0), _make_trade(3.0), _make_trade(-2.0)]
        assert MetricsCalculator.win_rate(trades) == 0.5

    def test_zero_pnl_not_counted_as_win(self):
        trades = [_make_trade(0.0), _make_trade(10.0)]
        assert MetricsCalculator.win_rate(trades) == 0.5

    def test_none_pnl_treated_as_zero(self):
        trade = _make_trade(0.0)
        trade.pnl = None
        assert MetricsCalculator.win_rate([trade]) == 0.0


class TestTotalPnl:
    def test_empty_trades(self):
        assert MetricsCalculator.total_pnl([]) == 0.0

    def test_sum_of_pnls(self):
        trades = [_make_trade(10.0), _make_trade(-5.0), _make_trade(3.0)]
        assert MetricsCalculator.total_pnl(trades) == 8.0

    def test_none_pnl_treated_as_zero(self):
        trade = _make_trade(0.0)
        trade.pnl = None
        trades = [_make_trade(10.0), trade]
        assert MetricsCalculator.total_pnl(trades) == 10.0


class TestMaxDrawdown:
    def test_empty_trades(self):
        assert MetricsCalculator.max_drawdown([]) == 0.0

    def test_no_drawdown_all_positive(self):
        trades = [_make_trade(10.0), _make_trade(5.0), _make_trade(3.0)]
        assert MetricsCalculator.max_drawdown(trades) == 0.0

    def test_simple_drawdown(self):
        trades = [_make_trade(10.0), _make_trade(-5.0), _make_trade(-3.0)]
        # Peak at 10, trough at 10-5-3=2, drawdown = 8
        assert MetricsCalculator.max_drawdown(trades) == 8.0

    def test_drawdown_recovery(self):
        trades = [_make_trade(10.0), _make_trade(-3.0), _make_trade(5.0), _make_trade(-8.0)]
        # Peak at 12 (10-3+5), trough at 4 (12-8), drawdown = 8
        assert MetricsCalculator.max_drawdown(trades) == 8.0

    def test_all_losses(self):
        trades = [_make_trade(-5.0), _make_trade(-3.0)]
        # Peak stays at 0, trough at -8, drawdown = 8
        assert MetricsCalculator.max_drawdown(trades) == 8.0


class TestSharpeRatio:
    def test_empty_trades(self):
        assert MetricsCalculator.sharpe_ratio([]) == 0.0

    def test_single_trade(self):
        assert MetricsCalculator.sharpe_ratio([_make_trade(10.0)]) == 0.0

    def test_zero_std(self):
        trades = [_make_trade(5.0), _make_trade(5.0), _make_trade(5.0)]
        assert MetricsCalculator.sharpe_ratio(trades) == 0.0

    def test_positive_sharpe(self):
        trades = [_make_trade(10.0), _make_trade(20.0)]
        result = MetricsCalculator.sharpe_ratio(trades)
        assert result > 0.0

    def test_with_risk_free_rate(self):
        trades = [_make_trade(10.0), _make_trade(20.0)]
        result_no_rfr = MetricsCalculator.sharpe_ratio(trades, risk_free_rate=0.0)
        result_with_rfr = MetricsCalculator.sharpe_ratio(trades, risk_free_rate=5.0)
        assert result_with_rfr < result_no_rfr


class TestProfitFactor:
    def test_empty_trades(self):
        assert MetricsCalculator.profit_factor([]) == 0.0

    def test_no_losing_trades(self):
        trades = [_make_trade(10.0), _make_trade(5.0)]
        assert MetricsCalculator.profit_factor(trades) == float("inf")

    def test_no_winning_trades(self):
        trades = [_make_trade(-10.0), _make_trade(-5.0)]
        assert MetricsCalculator.profit_factor(trades) == 0.0

    def test_equal_profit_and_loss(self):
        trades = [_make_trade(10.0), _make_trade(-10.0)]
        assert MetricsCalculator.profit_factor(trades) == 1.0

    def test_profit_factor_calculation(self):
        trades = [_make_trade(20.0), _make_trade(10.0), _make_trade(-5.0)]
        # gross_profit = 30, gross_loss = 5, factor = 6.0
        assert MetricsCalculator.profit_factor(trades) == 6.0

    def test_all_zero_pnl(self):
        trades = [_make_trade(0.0), _make_trade(0.0)]
        assert MetricsCalculator.profit_factor(trades) == 0.0


class TestAvgTradeDuration:
    def test_empty_trades(self):
        assert MetricsCalculator.avg_trade_duration([]) == 0.0

    def test_single_closed_trade(self):
        trades = [_make_trade(10.0, duration_seconds=3600)]
        assert MetricsCalculator.avg_trade_duration(trades) == 3600.0

    def test_multiple_closed_trades(self):
        trades = [
            _make_trade(10.0, duration_seconds=3600),
            _make_trade(-5.0, duration_seconds=7200),
        ]
        assert MetricsCalculator.avg_trade_duration(trades) == 5400.0

    def test_open_trades_excluded(self):
        closed = _make_trade(10.0, duration_seconds=3600)
        open_trade = _make_trade(0.0)  # no exit_time
        trades = [closed, open_trade]
        assert MetricsCalculator.avg_trade_duration(trades) == 3600.0

    def test_all_open_trades(self):
        trades = [_make_trade(0.0), _make_trade(0.0)]  # no exit_time
        assert MetricsCalculator.avg_trade_duration(trades) == 0.0
