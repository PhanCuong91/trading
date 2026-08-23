"""Broker data models, enums, and exceptions."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from forex_signals.data.models import Signal


class BrokerType(Enum):
    """Supported broker connection types."""

    SOCKET = "socket"
    MOCK = "mock"


class BrokerError(Exception):
    """Base exception for all broker operations."""

    pass


class BrokerConnectionError(BrokerError):
    """Raised when connecting or communicating with the broker fails."""

    pass


class BrokerExecutionError(BrokerError):
    """Raised when an order placement or close operation is rejected by the broker."""

    pass


class SpreadExceededError(BrokerError):
    """Raised when live market spread exceeds the configured maximum threshold."""

    pass


@dataclass(frozen=True)
class AccountInfo:
    """Live broker trading account metrics."""

    login: int
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int


@dataclass(frozen=True)
class SymbolInfo:
    """Broker currency pair specifications and trade constraints."""

    name: str
    digits: int
    point: float
    pip_size: float
    spread_points: int
    spread_pips: float
    min_lot: float
    max_lot: float
    lot_step: float
    stop_level_points: int
    trade_contract_size: float = 100000.0


@dataclass
class Position:
    """Active open position in the broker terminal."""

    ticket: int
    symbol: str
    direction: Signal
    volume: float
    open_price: float
    stop_loss: float
    take_profit: float
    open_time: datetime
    current_price: float
    profit: float
    magic: int
    comment: str = ""


@dataclass(frozen=True)
class TradeExecutionResult:
    """Outcome of a broker trade request (order send / position close)."""

    success: bool
    retcode: int
    ticket: Optional[int]
    order_id: Optional[str]
    price: float
    volume: float
    timestamp: datetime
    error_message: str = ""
