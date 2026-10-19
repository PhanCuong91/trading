"""MetaTrader 5 Direct Broker Client using official Python MetaTrader5 package."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from forex_signals.broker.models import (
    AccountInfo,
    BrokerConnectionError,
    BrokerError,
    BrokerExecutionError,
    Position,
    SymbolInfo,
    TradeExecutionResult,
)
from forex_signals.data.models import Candle, Signal, Timeframe

logger = logging.getLogger(__name__)

# Attempt to import MetaTrader5
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


class MT5BrokerClient:
    """Direct MetaTrader 5 client connecting via the official Python MetaTrader5 module."""

    def __init__(
        self,
        path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        timeout: int = 5000,
        portable: bool = False,
        mt5_module: Optional[Any] = None,
    ) -> None:
        """Initialize the MT5 Direct Broker Client.

        Args:
            path: Path to terminal64.exe executable (useful for Wine on Linux/Raspberry Pi).
            login: Account login number.
            password: Account password.
            server: Broker server name.
            timeout: Connection timeout in milliseconds.
            portable: Run terminal in portable mode.
            mt5_module: Optional injected mt5 module for testing/mocking.
        """
        self.path = path
        self.login = login
        self.password = password
        self.server = server
        self.timeout = timeout
        self.portable = portable
        self._mt5 = mt5_module or mt5
        self._connected = False

    def _ensure_mt5(self) -> Any:
        """Ensure MT5 module is available."""
        if self._mt5 is None:
            raise BrokerConnectionError(
                "MetaTrader5 Python package is not available in this environment. "
                "Please install MetaTrader5 or run in a compatible environment."
            )
        return self._mt5

    def connect(self) -> bool:
        """Initialize connection to MetaTrader 5 terminal.

        Returns:
            True if connection and login succeed.

        Raises:
            BrokerConnectionError: If connection fails.
        """
        m = self._ensure_mt5()

        init_kwargs: Dict[str, Any] = {}
        if self.path:
            init_kwargs["path"] = self.path
        if self.login:
            init_kwargs["login"] = int(self.login)
        if self.password:
            init_kwargs["password"] = str(self.password)
        if self.server:
            init_kwargs["server"] = str(self.server)
        if self.timeout:
            init_kwargs["timeout"] = int(self.timeout)
        if self.portable:
            init_kwargs["portable"] = bool(self.portable)

        logger.info("Initializing MetaTrader 5 terminal with params: %s", {k: v for k, v in init_kwargs.items() if k != "password"})
        success = m.initialize(**init_kwargs) if init_kwargs else m.initialize()
        if not success:
            last_err = m.last_error()
            raise BrokerConnectionError(f"Failed to initialize MetaTrader 5: {last_err}")

        # If login credentials provided and initialize didn't log in
        if self.login and self.password and self.server:
            login_success = m.login(login=int(self.login), password=str(self.password), server=str(self.server))
            if not login_success:
                last_err = m.last_error()
                m.shutdown()
                raise BrokerConnectionError(f"Failed to log into MT5 account {self.login}: {last_err}")

        self._connected = True
        logger.info("Successfully connected to MetaTrader 5.")
        return True

    def disconnect(self) -> None:
        """Disconnect and release MetaTrader 5 resources."""
        if self._connected and self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception as e:
                logger.warning("Error during MT5 shutdown: %s", e)
        self._connected = False

    def is_connected(self) -> bool:
        """Check if terminal is connected to broker trade server."""
        if not self._connected or self._mt5 is None:
            return False
        try:
            info = self._mt5.terminal_info()
            if info is None:
                return False
            return getattr(info, "connected", True)
        except Exception:
            return False

    def get_account_info(self) -> AccountInfo:
        """Retrieve live trading account balances and margin."""
        m = self._ensure_mt5()
        if not self._connected:
            raise BrokerConnectionError("MT5 broker client is not connected.")

        acc = m.account_info()
        if acc is None:
            raise BrokerConnectionError(f"Failed to fetch MT5 account info: {m.last_error()}")

        free_margin = getattr(acc, "margin_free", getattr(acc, "free_margin", 0.0))
        return AccountInfo(
            login=int(acc.login),
            server=str(acc.server),
            currency=str(acc.currency),
            balance=float(acc.balance),
            equity=float(acc.equity),
            margin=float(acc.margin),
            free_margin=float(free_margin),
            leverage=int(acc.leverage),
        )

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Fetch specification details and spread for a symbol."""
        m = self._ensure_mt5()
        if not self._connected:
            raise BrokerConnectionError("MT5 broker client is not connected.")

        # Ensure symbol is selected in Market Watch
        m.symbol_select(symbol, True)

        info = m.symbol_info(symbol)
        if info is None:
            raise BrokerError(f"Failed to fetch symbol info for '{symbol}': {m.last_error()}")

        digits = int(info.digits)
        point = float(info.point)
        # Determine pip size based on digits
        pip_size = 0.01 if digits in (2, 3) else 0.0001
        spread_points = int(info.spread)
        spread_pips = round((spread_points * point) / pip_size, 2)

        return SymbolInfo(
            name=str(info.name),
            digits=digits,
            point=point,
            pip_size=pip_size,
            spread_points=spread_points,
            spread_pips=spread_pips,
            min_lot=float(info.volume_min),
            max_lot=float(info.volume_max),
            lot_step=float(info.volume_step),
            stop_level_points=int(getattr(info, "trade_stops_level", getattr(info, "stops_level", 0))),
            trade_contract_size=float(getattr(info, "trade_contract_size", 100000.0)),
        )

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> List[Candle]:
        """Fetch latest completed candlestick history from MT5."""
        m = self._ensure_mt5()
        if not self._connected:
            raise BrokerConnectionError("MT5 broker client is not connected.")

        # Map Timeframe to MT5 timeframe constants
        tf_mapping = {
            Timeframe.M5: getattr(m, "TIMEFRAME_M5", 5),
            Timeframe.M15: getattr(m, "TIMEFRAME_M15", 15),
            Timeframe.H1: getattr(m, "TIMEFRAME_H1", 60 | 0x4000),
            Timeframe.H4: getattr(m, "TIMEFRAME_H4", 240 | 0x4000),
            Timeframe.D1: getattr(m, "TIMEFRAME_D1", 1440 | 0x4000),
        }
        # Support M1 and M30 if they exist on Timeframe
        if hasattr(Timeframe, "M1"):
            tf_mapping[getattr(Timeframe, "M1")] = getattr(m, "TIMEFRAME_M1", 1)
        if hasattr(Timeframe, "M30"):
            tf_mapping[getattr(Timeframe, "M30")] = getattr(m, "TIMEFRAME_M30", 30)
        mt5_tf = tf_mapping.get(timeframe)
        if mt5_tf is None:
            raise BrokerError(f"Unsupported timeframe: {timeframe}")

        rates = m.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None or len(rates) == 0:
            raise BrokerError(f"Failed to fetch rates for {symbol} ({timeframe.name}): {m.last_error()}")

        candles: List[Candle] = []
        for rate in rates:
            if isinstance(rate, dict):
                time_val = rate["time"]
                open_val = rate["open"]
                high_val = rate["high"]
                low_val = rate["low"]
                close_val = rate["close"]
                vol_val = rate.get("tick_volume", rate.get("volume", 0))
            elif hasattr(rate, "dtype") and getattr(rate.dtype, "names", None):
                time_val = rate["time"] if "time" in rate.dtype.names else rate[0]
                open_val = rate["open"] if "open" in rate.dtype.names else rate[1]
                high_val = rate["high"] if "high" in rate.dtype.names else rate[2]
                low_val = rate["low"] if "low" in rate.dtype.names else rate[3]
                close_val = rate["close"] if "close" in rate.dtype.names else rate[4]
                vol_val = rate["tick_volume"] if "tick_volume" in rate.dtype.names else (rate[5] if len(rate) > 5 else 0)
            elif hasattr(rate, "__getitem__"):
                time_val = rate[0]
                open_val = rate[1]
                high_val = rate[2]
                low_val = rate[3]
                close_val = rate[4]
                vol_val = rate[5] if len(rate) > 5 else 0
            else:
                time_val = getattr(rate, "time", 0)
                open_val = getattr(rate, "open", 0.0)
                high_val = getattr(rate, "high", 0.0)
                low_val = getattr(rate, "low", 0.0)
                close_val = getattr(rate, "close", 0.0)
                vol_val = getattr(rate, "tick_volume", getattr(rate, "volume", 0.0))

            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(time_val)),
                    open=float(open_val),
                    high=float(high_val),
                    low=float(low_val),
                    close=float(close_val),
                    volume=float(vol_val),
                )
            )

        candles.sort(key=lambda c: c.timestamp)
        return candles

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
        """Place a live market order via MT5."""
        m = self._ensure_mt5()
        if not self._connected:
            raise BrokerConnectionError("MT5 broker client is not connected.")

        tick = m.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerExecutionError(f"Could not get market tick for {symbol}: {m.last_error()}")

        order_type = getattr(m, "ORDER_TYPE_BUY", 0) if direction == Signal.BUY else getattr(m, "ORDER_TYPE_SELL", 1)
        price = float(tick.ask) if direction == Signal.BUY else float(tick.bid)

        request = {
            "action": getattr(m, "TRADE_ACTION_DEAL", 1),
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": float(sl_price),
            "tp": float(tp_price),
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": comment,
            "type_time": getattr(m, "ORDER_TIME_GTC", 0),
            "type_filling": getattr(m, "ORDER_FILLING_IOC", 1),
        }

        logger.info("Sending MT5 order: %s", request)
        result = m.order_send(request)
        if result is None:
            last_err = m.last_error()
            raise BrokerExecutionError(f"MT5 order_send returned None: {last_err}")

        trade_done = getattr(m, "TRADE_RETCODE_DONE", 10009)
        retcode = getattr(result, "retcode", None)
        if retcode != trade_done:
            # Try with ORDER_FILLING_FOK if IOC filling was rejected
            if getattr(result, "retcode", None) == getattr(m, "TRADE_RETCODE_INVALID_FILL", 10030):
                request["type_filling"] = getattr(m, "ORDER_FILLING_FOK", 0)
                result = m.order_send(request)
                retcode = getattr(result, "retcode", None)

        if retcode != trade_done:
            err_msg = getattr(result, "comment", f"Error retcode {retcode}")
            raise BrokerExecutionError(f"Order rejected by MT5 (retcode {retcode}): {err_msg}")

        ticket = getattr(result, "order", getattr(result, "deal", None))
        fill_price = float(getattr(result, "price", price))
        fill_volume = float(getattr(result, "volume", volume))

        return TradeExecutionResult(
            success=True,
            retcode=int(retcode),
            ticket=int(ticket) if ticket is not None else None,
            order_id=str(ticket) if ticket is not None else None,
            price=fill_price,
            volume=fill_volume,
            timestamp=datetime.now(),
        )

    def close_position(self, ticket: int, deviation: int = 10) -> TradeExecutionResult:
        """Close an open position by ticket number."""
        m = self._ensure_mt5()
        if not self._connected:
            raise BrokerConnectionError("MT5 broker client is not connected.")

        positions = m.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            raise BrokerExecutionError(f"Position ticket {ticket} not found in MT5.")

        pos = positions[0]
        pos_type = getattr(pos, "type", 0)
        buy_type = getattr(m, "ORDER_TYPE_BUY", 0)
        sell_type = getattr(m, "ORDER_TYPE_SELL", 1)

        close_type = sell_type if pos_type == buy_type else buy_type
        symbol = str(getattr(pos, "symbol", ""))

        tick = m.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerExecutionError(f"Could not get tick for {symbol} to close position {ticket}.")

        close_price = float(tick.bid) if pos_type == buy_type else float(tick.ask)
        volume = float(getattr(pos, "volume", 0.0))
        magic = int(getattr(pos, "magic", 0))

        request = {
            "action": getattr(m, "TRADE_ACTION_DEAL", 1),
            "position": int(ticket),
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "price": close_price,
            "deviation": int(deviation),
            "magic": magic,
            "comment": "Close position",
            "type_time": getattr(m, "ORDER_TIME_GTC", 0),
            "type_filling": getattr(m, "ORDER_FILLING_IOC", 1),
        }

        logger.info("Sending MT5 position close: %s", request)
        result = m.order_send(request)
        if result is None:
            raise BrokerExecutionError(f"MT5 order_send returned None during close: {m.last_error()}")

        trade_done = getattr(m, "TRADE_RETCODE_DONE", 10009)
        retcode = getattr(result, "retcode", None)
        if retcode != trade_done:
            err_msg = getattr(result, "comment", f"Error retcode {retcode}")
            raise BrokerExecutionError(f"Failed to close position {ticket} (retcode {retcode}): {err_msg}")

        return TradeExecutionResult(
            success=True,
            retcode=int(retcode),
            ticket=ticket,
            order_id=str(ticket),
            price=float(getattr(result, "price", close_price)),
            volume=float(getattr(result, "volume", volume)),
            timestamp=datetime.now(),
        )

    def get_open_positions(self, magic: Optional[int] = None) -> List[Position]:
        """Query currently open MT5 positions, optionally filtered by magic number."""
        m = self._ensure_mt5()
        if not self._connected:
            raise BrokerConnectionError("MT5 broker client is not connected.")

        positions = m.positions_get()
        if positions is None:
            return []

        result: List[Position] = []
        buy_type = getattr(m, "ORDER_TYPE_BUY", 0)

        for pos in positions:
            pos_magic = int(getattr(pos, "magic", 0))
            if magic is not None and pos_magic != magic:
                continue

            pos_type = getattr(pos, "type", 0)
            direction = Signal.BUY if pos_type == buy_type else Signal.SELL

            time_val = getattr(pos, "time", 0)
            open_time = datetime.fromtimestamp(int(time_val)) if time_val else datetime.now()

            result.append(
                Position(
                    ticket=int(getattr(pos, "ticket", 0)),
                    symbol=str(getattr(pos, "symbol", "")),
                    direction=direction,
                    volume=float(getattr(pos, "volume", 0.0)),
                    open_price=float(getattr(pos, "price_open", 0.0)),
                    stop_loss=float(getattr(pos, "sl", 0.0)),
                    take_profit=float(getattr(pos, "tp", 0.0)),
                    open_time=open_time,
                    current_price=float(getattr(pos, "price_current", 0.0)),
                    profit=float(getattr(pos, "profit", 0.0)),
                    magic=pos_magic,
                    comment=str(getattr(pos, "comment", "")),
                )
            )

        return result
