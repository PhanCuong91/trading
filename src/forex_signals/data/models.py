"""Data models and enums for the forex trading signal system."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional


class Timeframe(Enum):
    """Supported candlestick timeframes."""

    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class Signal(Enum):
    """Trading signal direction."""

    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class OrderStatus(Enum):
    """Order lifecycle status."""

    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"


@dataclass(frozen=True)
class Candle:
    """OHLCV candlestick data point."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class StrategySignal:
    """Signal produced by a single strategy."""

    strategy_name: str
    signal: Signal
    timestamp: datetime


@dataclass
class Order:
    """Trading order with lifecycle tracking."""

    direction: Signal  # BUY or SELL only
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.OPEN
    pnl: Optional[float] = None


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for a backtest run."""

    pair: str
    timeframe: Timeframe
    sl_pips: float
    tp_pips: float
    start_date: datetime
    end_date: datetime


@dataclass(frozen=True)
class BacktestResult:
    """Results and metrics from a completed backtest."""

    trades: List[Order]
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float
    avg_trade_duration_seconds: float
    num_trades: int
