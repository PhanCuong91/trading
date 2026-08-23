"""Mock Broker Client for offline testing, property verification, and CI pipelines."""

from datetime import datetime
from typing import Dict, List, Optional

from forex_signals.broker.models import (
    AccountInfo,
    BrokerConnectionError,
    BrokerExecutionError,
    Position,
    SymbolInfo,
    TradeExecutionResult,
)
from forex_signals.data.models import Candle, Signal, Timeframe


class MockBrokerClient:
    """In-memory mock broker simulating MT5 broker interactions."""

    def __init__(
        self,
        initial_balance: float = 10000.0,
        currency: str = "USD",
        leverage: int = 100,
    ):
        """Initialize mock broker."""
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.currency = currency
        self.leverage = leverage
        self._connected = False
        self._ticket_counter = 1000001
        self._positions: Dict[int, Position] = {}
        self._custom_candles: Dict[str, List[Candle]] = {}
        self._symbol_specs: Dict[str, SymbolInfo] = {
            "EURUSD": SymbolInfo(
                name="EURUSD",
                digits=5,
                point=0.00001,
                pip_size=0.0001,
                spread_points=12,
                spread_pips=1.2,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
                stop_level_points=0,
                trade_contract_size=100000.0,
            ),
            "EURUSD=X": SymbolInfo(
                name="EURUSD=X",
                digits=5,
                point=0.00001,
                pip_size=0.0001,
                spread_points=12,
                spread_pips=1.2,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
                stop_level_points=0,
                trade_contract_size=100000.0,
            ),
            "USDJPY": SymbolInfo(
                name="USDJPY",
                digits=3,
                point=0.001,
                pip_size=0.01,
                spread_points=15,
                spread_pips=1.5,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
                stop_level_points=0,
                trade_contract_size=100000.0,
            ),
        }
        self._current_prices: Dict[str, float] = {
            "EURUSD": 1.08500,
            "EURUSD=X": 1.08500,
            "USDJPY": 150.250,
        }

    def connect(self) -> bool:
        """Simulate connecting to broker."""
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Simulate disconnecting from broker."""
        self._connected = False

    def is_connected(self) -> bool:
        """Return mock connection state."""
        return self._connected

    def get_account_info(self) -> AccountInfo:
        """Return simulated account info."""
        if not self._connected:
            raise BrokerConnectionError("Mock broker is not connected.")

        open_profit = sum(p.profit for p in self._positions.values())
        equity = self.balance + open_profit
        margin = sum(
            (p.volume * 100000.0 / self.leverage) for p in self._positions.values()
        )
        free_margin = equity - margin

        return AccountInfo(
            login=999999,
            server="Mock-Server",
            currency=self.currency,
            balance=round(self.balance, 2),
            equity=round(equity, 2),
            margin=round(margin, 2),
            free_margin=round(free_margin, 2),
            leverage=self.leverage,
        )

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Return symbol specifications."""
        if not self._connected:
            raise BrokerConnectionError("Mock broker is not connected.")

        if symbol in self._symbol_specs:
            return self._symbol_specs[symbol]

        # Generate default 5-digit spec for unknown symbols
        return SymbolInfo(
            name=symbol,
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=15,
            spread_pips=1.5,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=0,
            trade_contract_size=100000.0,
        )

    def set_symbol_info(self, symbol_info: SymbolInfo) -> None:
        """Register custom symbol spec for testing."""
        self._symbol_specs[symbol_info.name] = symbol_info

    def set_candles(self, symbol: str, candles: List[Candle]) -> None:
        """Set simulated candle history for a symbol."""
        self._custom_candles[symbol] = list(candles)
        if candles:
            self._current_prices[symbol] = candles[-1].close

    def set_price(self, symbol: str, price: float) -> None:
        """Update current market price for a symbol."""
        self._current_prices[symbol] = price
        # Update profits of open positions for this symbol
        for p in self._positions.values():
            if p.symbol == symbol:
                p.current_price = price
                if p.direction == Signal.BUY:
                    diff = price - p.open_price
                else:
                    diff = p.open_price - price
                p.profit = round(diff * p.volume * 100000.0, 2)

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> List[Candle]:
        """Return candle series."""
        if not self._connected:
            raise BrokerConnectionError("Mock broker is not connected.")

        candles = self._custom_candles.get(symbol, [])
        if not candles:
            # Generate synthetic candles if none provided
            now = datetime.now()
            base_price = self._current_prices.get(symbol, 1.08500)
            candles = [
                Candle(
                    timestamp=now,
                    open=base_price,
                    high=base_price + 0.0005,
                    low=base_price - 0.0005,
                    close=base_price,
                    volume=100.0,
                )
            ]
        return candles[-count:]

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
        """Simulate order execution."""
        if not self._connected:
            raise BrokerConnectionError("Mock broker is not connected.")

        if direction not in (Signal.BUY, Signal.SELL):
            raise BrokerExecutionError(f"Invalid direction: {direction}")

        spec = self.get_symbol_info(symbol)
        if volume < spec.min_lot or volume > spec.max_lot:
            raise BrokerExecutionError(
                f"Volume {volume} out of range [{spec.min_lot}, {spec.max_lot}]"
            )

        ticket = self._ticket_counter
        self._ticket_counter += 1
        entry_price = self._current_prices.get(symbol, 1.08500)
        now = datetime.now()

        pos = Position(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=entry_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            open_time=now,
            current_price=entry_price,
            profit=0.0,
            magic=magic,
            comment=comment,
        )
        self._positions[ticket] = pos

        return TradeExecutionResult(
            success=True,
            retcode=10009,
            ticket=ticket,
            order_id=str(ticket),
            price=entry_price,
            volume=volume,
            timestamp=now,
            error_message="",
        )

    def close_position(self, ticket: int, deviation: int = 10) -> TradeExecutionResult:
        """Simulate position close."""
        if not self._connected:
            raise BrokerConnectionError("Mock broker is not connected.")

        if ticket not in self._positions:
            raise BrokerExecutionError(f"Position ticket {ticket} not found.")

        pos = self._positions.pop(ticket)
        close_price = self._current_prices.get(pos.symbol, pos.open_price)
        self.balance += pos.profit

        return TradeExecutionResult(
            success=True,
            retcode=10009,
            ticket=ticket,
            order_id=str(ticket),
            price=close_price,
            volume=pos.volume,
            timestamp=datetime.now(),
            error_message="",
        )

    def get_open_positions(self, magic: Optional[int] = None) -> List[Position]:
        """Return all open positions, optionally filtered by magic number."""
        if not self._connected:
            raise BrokerConnectionError("Mock broker is not connected.")

        if magic is None:
            return list(self._positions.values())
        return [p for p in self._positions.values() if p.magic == magic]
