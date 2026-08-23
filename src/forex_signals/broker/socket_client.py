"""TCP Socket Client connecting to MT5 ForexBridge.mq5 Expert Advisor (Method A)."""

import json
import logging
import socket
import time
from datetime import datetime, timezone
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


class SocketBrokerClient:
    """TCP Socket Client for MetaTrader 5 Expert Advisor (Method A)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5555,
        timeout: float = 5.0,
        max_reconnect_attempts: int = 3,
    ):
        """Initialize the socket broker client.

        Args:
            host: Server hostname or IP where ForexBridge.mq5 is running.
            port: Server port (default 5555).
            timeout: Socket timeout in seconds.
            max_reconnect_attempts: Max attempts to reconnect on failure.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_reconnect_attempts = max_reconnect_attempts
        self._sock: Optional[socket.socket] = None
        self._buffer = ""

    def connect(self) -> bool:
        """Connect to the ForexBridge.mq5 socket server.

        Returns:
            True if connection established and validated via PING.

        Raises:
            BrokerConnectionError: If connection cannot be established.
        """
        if self._sock is not None:
            self.disconnect()

        last_error = None
        for attempt in range(1, self.max_reconnect_attempts + 1):
            try:
                logger.info(
                    "Connecting to MT5 Socket Bridge at %s:%d (attempt %d/%d)...",
                    self.host,
                    self.port,
                    attempt,
                    self.max_reconnect_attempts,
                )
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                self._sock = sock
                self._buffer = ""

                # Validate with PING
                response = self._send_request({"action": "PING"})
                if response.get("status") == "OK":
                    logger.info("Successfully connected to MT5 Socket Bridge.")
                    return True
                else:
                    raise BrokerConnectionError(
                        f"Unexpected ping response: {response}"
                    )
            except (socket.error, socket.timeout, BrokerError) as e:
                last_error = e
                self.disconnect()
                if attempt < self.max_reconnect_attempts:
                    sleep_time = 0.5 * (2 ** (attempt - 1))
                    logger.warning(
                        "Connection attempt %d failed (%s). Retrying in %.1fs...",
                        attempt,
                        e,
                        sleep_time,
                    )
                    time.sleep(sleep_time)

        raise BrokerConnectionError(
            f"Failed to connect to MT5 Bridge at {self.host}:{self.port} after "
            f"{self.max_reconnect_attempts} attempts: {last_error}"
        )

    def disconnect(self) -> None:
        """Disconnect and close socket."""
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = ""

    def is_connected(self) -> bool:
        """Check if socket connection is alive."""
        if self._sock is None:
            return False
        try:
            res = self._send_request({"action": "PING"})
            return res.get("status") == "OK"
        except Exception:
            return False

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON request and receive newline-delimited JSON response."""
        if self._sock is None:
            raise BrokerConnectionError("Socket client is not connected.")

        try:
            req_str = json.dumps(request) + "\n"
            self._sock.sendall(req_str.encode("utf-8"))

            while "\n" not in self._buffer:
                chunk = self._sock.recv(4096)
                if not chunk:
                    raise BrokerConnectionError("Connection closed by MT5 server.")
                self._buffer += chunk.decode("utf-8")

            line, self._buffer = self._buffer.split("\n", 1)
            response = json.loads(line.strip())
            return response
        except socket.timeout as e:
            raise BrokerConnectionError(f"Socket request timed out: {e}") from e
        except (socket.error, json.JSONDecodeError) as e:
            self.disconnect()
            raise BrokerConnectionError(f"Socket communication error: {e}") from e

    def get_account_info(self) -> AccountInfo:
        """Fetch live account balance, equity, and margin."""
        res = self._send_request({"action": "ACCOUNT_INFO"})
        if res.get("status") != "OK":
            raise BrokerError(res.get("error_message", "Failed to get account info"))

        return AccountInfo(
            login=int(res["login"]),
            server=str(res.get("server", "")),
            currency=str(res.get("currency", "USD")),
            balance=float(res["balance"]),
            equity=float(res["equity"]),
            margin=float(res["margin"]),
            free_margin=float(res["free_margin"]),
            leverage=int(res["leverage"]),
        )

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Fetch symbol specifications and live spread."""
        res = self._send_request({"action": "SYMBOL_INFO", "symbol": symbol})
        if res.get("status") != "OK":
            raise BrokerError(res.get("error_message", f"Failed to get symbol info for {symbol}"))

        digits = int(res["digits"])
        point = float(res["point"])
        pip_size = float(res.get("pip_size", point * 10 if digits in (3, 5) else point))
        spread_pts = int(res.get("spread_points", 0))
        spread_pips = float(res.get("spread_pips", spread_pts * point / pip_size if pip_size > 0 else 0.0))

        return SymbolInfo(
            name=str(res.get("symbol", symbol)),
            digits=digits,
            point=point,
            pip_size=pip_size,
            spread_points=spread_pts,
            spread_pips=spread_pips,
            min_lot=float(res.get("min_lot", 0.01)),
            max_lot=float(res.get("max_lot", 100.0)),
            lot_step=float(res.get("lot_step", 0.01)),
            stop_level_points=int(res.get("stop_level", 0)),
            trade_contract_size=float(res.get("contract_size", 100000.0)),
        )

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> List[Candle]:
        """Fetch historical candle rates from MT5."""
        res = self._send_request(
            {
                "action": "GET_CANDLES",
                "symbol": symbol,
                "timeframe": timeframe.name,
                "count": count,
            }
        )
        if res.get("status") != "OK":
            raise BrokerError(res.get("error_message", f"Failed to fetch candles for {symbol}"))

        raw_candles = res.get("candles", [])
        candles: List[Candle] = []
        for c in raw_candles:
            ts = c["timestamp"]
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            else:
                dt = datetime.fromisoformat(str(ts))

            candles.append(
                Candle(
                    timestamp=dt,
                    open=float(c["open"]),
                    high=float(c["high"]),
                    low=float(c["low"]),
                    close=float(c["close"]),
                    volume=float(c.get("volume", 0.0)),
                )
            )
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
        """Send market order to MT5 via socket."""
        if direction not in (Signal.BUY, Signal.SELL):
            raise ValueError(f"Cannot place order with direction {direction}")

        req = {
            "action": "ORDER_SEND",
            "symbol": symbol,
            "type": direction.value,
            "volume": volume,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
        }
        res = self._send_request(req)
        now = datetime.now()

        if res.get("status") == "OK":
            return TradeExecutionResult(
                success=True,
                retcode=int(res.get("retcode", 10009)),
                ticket=int(res["ticket"]) if "ticket" in res else None,
                order_id=str(res.get("ticket", "")),
                price=float(res.get("price", 0.0)),
                volume=float(res.get("volume", volume)),
                timestamp=now,
                error_message="",
            )
        else:
            retcode = int(res.get("retcode", -1))
            err_msg = str(res.get("error_message", "Order rejected by broker"))
            raise BrokerExecutionError(f"MT5 Order Rejected (retcode {retcode}): {err_msg}")

    def close_position(self, ticket: int, deviation: int = 10) -> TradeExecutionResult:
        """Close open position by ticket."""
        req = {
            "action": "ORDER_CLOSE",
            "ticket": ticket,
            "deviation": deviation,
        }
        res = self._send_request(req)
        now = datetime.now()

        if res.get("status") == "OK":
            return TradeExecutionResult(
                success=True,
                retcode=int(res.get("retcode", 10009)),
                ticket=ticket,
                order_id=str(ticket),
                price=float(res.get("price", 0.0)),
                volume=float(res.get("volume", 0.0)),
                timestamp=now,
                error_message="",
            )
        else:
            retcode = int(res.get("retcode", -1))
            err_msg = str(res.get("error_message", "Position close failed"))
            raise BrokerExecutionError(f"MT5 Position Close Failed (retcode {retcode}): {err_msg}")

    def get_open_positions(self, magic: Optional[int] = None) -> List[Position]:
        """Fetch open positions matching magic number."""
        req: Dict[str, Any] = {"action": "GET_POSITIONS"}
        if magic is not None:
            req["magic"] = magic

        res = self._send_request(req)
        if res.get("status") != "OK":
            raise BrokerError(res.get("error_message", "Failed to fetch positions"))

        raw_positions = res.get("positions", [])
        positions: List[Position] = []
        for p in raw_positions:
            ts = p["open_time"]
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            else:
                dt = datetime.fromisoformat(str(ts))

            positions.append(
                Position(
                    ticket=int(p["ticket"]),
                    symbol=str(p["symbol"]),
                    direction=Signal(p["type"]),
                    volume=float(p["volume"]),
                    open_price=float(p["open_price"]),
                    stop_loss=float(p.get("sl", 0.0)),
                    take_profit=float(p.get("tp", 0.0)),
                    open_time=dt,
                    current_price=float(p.get("current_price", p["open_price"])),
                    profit=float(p.get("profit", 0.0)),
                    magic=int(p.get("magic", 0)),
                    comment=str(p.get("comment", "")),
                )
            )
        return positions
