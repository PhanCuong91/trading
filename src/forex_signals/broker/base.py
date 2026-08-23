"""Broker protocol definition for live and simulated execution."""

from typing import List, Optional, Protocol

from forex_signals.broker.models import (
    AccountInfo,
    Position,
    SymbolInfo,
    TradeExecutionResult,
)
from forex_signals.data.models import Candle, Signal, Timeframe


class Broker(Protocol):
    """Abstract broker interface for live socket and mock trading."""

    def connect(self) -> bool:
        """Establish connection to the broker terminal or server.

        Returns:
            True if connection is successful.

        Raises:
            BrokerConnectionError: If connection cannot be established.
        """
        ...

    def disconnect(self) -> None:
        """Cleanly disconnect and release broker resources."""
        ...

    def is_connected(self) -> bool:
        """Check if connection to broker is currently alive and active."""
        ...

    def get_account_info(self) -> AccountInfo:
        """Fetch current account balances, equity, and margin.

        Returns:
            AccountInfo dataclass with real-time account status.

        Raises:
            BrokerConnectionError: If broker communication fails.
        """
        ...

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Fetch specification details and current spread for a symbol.

        Args:
            symbol: Symbol name (e.g. 'EURUSD').

        Returns:
            SymbolInfo dataclass.

        Raises:
            BrokerError: If symbol is invalid or cannot be fetched.
        """
        ...

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> List[Candle]:
        """Fetch recent candlestick history directly from broker buffer.

        Args:
            symbol: Symbol name (e.g. 'EURUSD').
            timeframe: Candle timeframe enum.
            count: Number of completed historical candles to fetch.

        Returns:
            List of Candle objects sorted oldest to newest.

        Raises:
            BrokerError: If candles cannot be fetched.
        """
        ...

    def place_order(
        self,
        symbol: str,
        direction: Signal,
        volume: float,
        sl_price: float,
        tp_price: float,
        deviation: int = 10,
        magic: int = 100101,
        comment: str = "forex_signals_bot",
    ) -> TradeExecutionResult:
        """Place a market buy or sell order.

        Args:
            symbol: Symbol name to trade.
            direction: Signal.BUY or Signal.SELL.
            volume: Lot size (e.g. 0.1).
            sl_price: Calculated stop-loss price.
            tp_price: Calculated take-profit price.
            deviation: Allowed slippage in points.
            magic: Magic number for bot trade isolation.
            comment: Optional trade comment.

        Returns:
            TradeExecutionResult containing success flag, ticket, fill price, and retcode.

        Raises:
            BrokerExecutionError: If broker rejects the trade.
        """
        ...

    def close_position(self, ticket: int, deviation: int = 10) -> TradeExecutionResult:
        """Close an active position by its ticket number.

        Args:
            ticket: Broker position ticket.
            deviation: Allowed slippage in points.

        Returns:
            TradeExecutionResult detailing the close transaction.

        Raises:
            BrokerExecutionError: If position cannot be closed.
        """
        ...

    def get_open_positions(self, magic: Optional[int] = None) -> List[Position]:
        """Fetch all currently open positions, optionally filtered by magic number.

        Args:
            magic: Optional magic number filter.

        Returns:
            List of active Position objects.

        Raises:
            BrokerConnectionError: If broker communication fails.
        """
        ...
