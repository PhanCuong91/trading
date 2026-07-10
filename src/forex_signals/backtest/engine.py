"""Backtest engine orchestrator for running strategies against historical data."""

from typing import List, Optional

from forex_signals.backtest.metrics import MetricsCalculator
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import (
    BacktestResult,
    Candle,
    Order,
    OrderStatus,
    Signal,
    StrategySignal,
)
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies.base import Strategy


class BacktestEngine:
    """Orchestrates backtesting across historical data."""

    def __init__(
        self,
        strategies: List[Strategy],
        consensus: ConsensusEngine,
        order_manager: OrderManager,
    ):
        self.strategies = strategies
        self.consensus = consensus
        self.order_manager = order_manager

    def run(self, candles: List[Candle]) -> BacktestResult:
        """
        Process candles sequentially:
        1. For each candle, generate signals from all strategies
        2. Evaluate consensus
        3. If signal and no open position, create order
        4. Update open orders against current candle
        5. After all candles, compute metrics
        """
        all_orders: List[Order] = []
        open_order: Optional[Order] = None

        for i, candle in enumerate(candles):
            candles_so_far = candles[: i + 1]

            # Generate signals from strategies that have enough data
            strategy_signals: List[StrategySignal] = []
            for strategy in self.strategies:
                if len(candles_so_far) >= strategy.min_candles:
                    signal = strategy.generate_signal(candles_so_far)
                    strategy_signals.append(
                        StrategySignal(
                            strategy_name=strategy.name,
                            signal=signal,
                            timestamp=candle.timestamp,
                        )
                    )

            # Evaluate consensus
            consensus_signal = Signal.NEUTRAL
            if strategy_signals:
                consensus_signal = self.consensus.evaluate(strategy_signals)

            # Create order if signal and no open position
            if consensus_signal in (Signal.BUY, Signal.SELL) and open_order is None:
                open_order = self.order_manager.create_order(
                    direction=consensus_signal,
                    entry_price=candle.close,
                    entry_time=candle.timestamp,
                )
                all_orders.append(open_order)

            # Update open order against current candle
            if open_order is not None and open_order.status == OrderStatus.OPEN:
                self.order_manager.update_order(open_order, candle)
                if open_order.status != OrderStatus.OPEN:
                    open_order = None

        # Collect closed trades for metrics
        closed_trades = [o for o in all_orders if o.status != OrderStatus.OPEN]

        return BacktestResult(
            trades=closed_trades,
            win_rate=MetricsCalculator.win_rate(closed_trades),
            total_pnl=MetricsCalculator.total_pnl(closed_trades),
            max_drawdown=MetricsCalculator.max_drawdown(closed_trades),
            sharpe_ratio=MetricsCalculator.sharpe_ratio(closed_trades),
            profit_factor=MetricsCalculator.profit_factor(closed_trades),
            avg_trade_duration_seconds=MetricsCalculator.avg_trade_duration(
                closed_trades
            ),
            num_trades=len(closed_trades),
        )
