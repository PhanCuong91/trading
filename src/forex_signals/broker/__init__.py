"""Broker module supporting MetaTrader 5 Direct Python module and Mock simulation."""
from forex_signals.broker.base import Broker
from forex_signals.broker.live_runner import (
    LiveTradingEngine,
    adjust_sl_tp_for_stoplevel,
    quantize_lot_size,
)
from forex_signals.broker.mock import MockBrokerClient
from forex_signals.broker.models import (
    AccountInfo,
    BrokerConnectionError,
    BrokerError,
    BrokerExecutionError,
    BrokerType,
    Position,
    SpreadExceededError,
    SymbolInfo,
    TradeExecutionResult,
)
from forex_signals.broker.mt5_client import MT5BrokerClient

__all__ = [
    "Broker",
    "BrokerType",
    "BrokerError",
    "BrokerConnectionError",
    "BrokerExecutionError",
    "SpreadExceededError",
    "AccountInfo",
    "SymbolInfo",
    "Position",
    "TradeExecutionResult",
    "MT5BrokerClient",
    "MockBrokerClient",
    "LiveTradingEngine",
    "quantize_lot_size",
    "adjust_sl_tp_for_stoplevel",
]
