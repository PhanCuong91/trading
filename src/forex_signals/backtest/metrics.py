"""Performance metrics calculator for backtest results."""

import statistics
from typing import List

from forex_signals.data.models import Order


class MetricsCalculator:
    """Pure functions for computing backtest performance metrics."""

    @staticmethod
    def win_rate(trades: List[Order]) -> float:
        """Winning trades / total trades. Returns 0.0 if no trades."""
        if not trades:
            return 0.0
        winning = sum(1 for t in trades if (t.pnl or 0.0) > 0)
        return winning / len(trades)

    @staticmethod
    def total_pnl(trades: List[Order]) -> float:
        """Sum of all trade PnLs."""
        if not trades:
            return 0.0
        return sum(t.pnl if t.pnl is not None else 0.0 for t in trades)

    @staticmethod
    def max_drawdown(trades: List[Order]) -> float:
        """
        Maximum peak-to-trough decline in cumulative equity.
        Returns a non-negative value (0 means no drawdown).
        """
        if not trades:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in trades:
            pnl = trade.pnl if trade.pnl is not None else 0.0
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    @staticmethod
    def sharpe_ratio(trades: List[Order], risk_free_rate: float = 0.0) -> float:
        """
        (mean_return - risk_free_rate) / std_return.
        Returns 0.0 if fewer than 2 trades or zero std.
        """
        if len(trades) < 2:
            return 0.0

        returns = [t.pnl if t.pnl is not None else 0.0 for t in trades]
        std = statistics.stdev(returns)

        if std == 0.0:
            return 0.0

        mean = statistics.mean(returns)
        return (mean - risk_free_rate) / std

    @staticmethod
    def profit_factor(trades: List[Order]) -> float:
        """
        Gross profit / gross loss. Returns inf if no losing trades,
        0.0 if no winning trades.
        """
        if not trades:
            return 0.0

        gross_profit = sum(
            t.pnl for t in trades if t.pnl is not None and t.pnl > 0
        )
        gross_loss = sum(
            t.pnl for t in trades if t.pnl is not None and t.pnl < 0
        )

        if gross_profit == 0.0 and gross_loss == 0.0:
            return 0.0

        if gross_loss == 0.0:
            # No losing trades but has winning trades
            if gross_profit > 0.0:
                return float("inf")
            return 0.0

        if gross_profit == 0.0:
            return 0.0

        return gross_profit / abs(gross_loss)

    @staticmethod
    def avg_trade_duration(trades: List[Order]) -> float:
        """Average duration in seconds across all closed trades."""
        if not trades:
            return 0.0

        closed_trades = [
            t for t in trades if t.entry_time is not None and t.exit_time is not None
        ]

        if not closed_trades:
            return 0.0

        total_seconds = sum(
            (t.exit_time - t.entry_time).total_seconds() for t in closed_trades
        )
        return total_seconds / len(closed_trades)
