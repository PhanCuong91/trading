"""Unit tests for SocketBrokerClient using a mock TCP server fixture."""

import json
import socket
import threading
import time
from typing import Dict

import pytest

from forex_signals.broker.models import BrokerConnectionError, BrokerExecutionError
from forex_signals.broker.socket_client import SocketBrokerClient
from forex_signals.data.models import Signal, Timeframe


class MockSocketServer:
    """Lightweight in-process TCP server simulating ForexBridge.mq5."""

    def __init__(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", 0))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(5)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.custom_handlers: Dict[str, dict] = {}

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        try:
            # Connect dummy client to unblock accept
            dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dummy.connect(("127.0.0.1", self.port))
            dummy.close()
        except Exception:
            pass
        self.server_sock.close()
        self._thread.join(timeout=2.0)

    def _handle_request(self, req: dict) -> dict:
        action = req.get("action")
        if action in self.custom_handlers:
            return self.custom_handlers[action]

        if action == "PING":
            return {"status": "OK", "time": "2026-08-19 22:00:00", "server": "MockServer"}
        if action == "ACCOUNT_INFO":
            return {
                "status": "OK",
                "login": 123456,
                "server": "MockServer",
                "currency": "USD",
                "balance": 10000.0,
                "equity": 10000.0,
                "margin": 0.0,
                "free_margin": 10000.0,
                "leverage": 100,
            }
        if action == "SYMBOL_INFO":
            sym = req.get("symbol", "EURUSD")
            return {
                "status": "OK",
                "symbol": sym,
                "digits": 5,
                "point": 0.00001,
                "pip_size": 0.0001,
                "spread_points": 12,
                "spread_pips": 1.2,
                "min_lot": 0.01,
                "max_lot": 100.0,
                "lot_step": 0.01,
                "stop_level": 0,
                "contract_size": 100000.0,
            }
        if action == "GET_CANDLES":
            return {
                "status": "OK",
                "count": 2,
                "candles": [
                    {
                        "timestamp": 1783680000,
                        "open": 1.0850,
                        "high": 1.0860,
                        "low": 1.0840,
                        "close": 1.0855,
                        "volume": 100,
                    },
                    {
                        "timestamp": 1783680300,
                        "open": 1.0855,
                        "high": 1.0865,
                        "low": 1.0850,
                        "close": 1.0860,
                        "volume": 150,
                    },
                ],
            }
        if action == "ORDER_SEND":
            if req.get("volume", 0) > 500:
                return {"status": "ERROR", "retcode": 10014, "error_message": "Invalid volume"}
            return {
                "status": "OK",
                "ticket": 7891234,
                "price": 1.08550,
                "retcode": 10009,
                "volume": req.get("volume", 0.1),
                "comment": "Done",
            }
        if action == "ORDER_CLOSE":
            return {"status": "OK", "ticket": req.get("ticket"), "retcode": 10009, "comment": "Closed"}
        if action == "GET_POSITIONS":
            return {
                "status": "OK",
                "count": 1,
                "positions": [
                    {
                        "ticket": 7891234,
                        "symbol": "EURUSD",
                        "type": "BUY",
                        "volume": 0.1,
                        "open_price": 1.08550,
                        "sl": 1.08350,
                        "tp": 1.08950,
                        "open_time": 1783680000,
                        "current_price": 1.08600,
                        "profit": 5.0,
                        "magic": 100101,
                        "comment": "test_bot",
                    }
                ],
            }

        return {"status": "ERROR", "error_message": f"Unknown action: {action}"}

    def _run(self):
        while not self._stop_event.is_set():
            try:
                client_sock, _ = self.server_sock.accept()
            except Exception:
                break

            client_sock.settimeout(1.0)
            buffer = ""
            while not self._stop_event.is_set():
                try:
                    data = client_sock.recv(4096)
                    if not data:
                        break
                    buffer += data.decode("utf-8")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if not line.strip():
                            continue
                        req = json.loads(line.strip())
                        resp = self._handle_request(req)
                        client_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except Exception:
                    break
            try:
                client_sock.close()
            except Exception:
                pass


@pytest.fixture
def mock_server():
    """Start and stop MockSocketServer for testing."""
    server = MockSocketServer()
    server.start()
    time.sleep(0.05)
    yield server
    server.stop()


class TestSocketBrokerClient:
    """Tests for SocketBrokerClient communicating with MT5 bridge."""

    def test_connect_and_ping(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        assert client.connect() is True
        assert client.is_connected() is True
        client.disconnect()
        assert client.is_connected() is False

    def test_connect_failure_raises(self):
        # Port 59999 where nothing is running
        client = SocketBrokerClient(host="127.0.0.1", port=59999, timeout=0.2, max_reconnect_attempts=2)
        with pytest.raises(BrokerConnectionError):
            client.connect()

    def test_get_account_info(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        acc = client.get_account_info()
        assert acc.login == 123456
        assert acc.balance == 10000.0
        assert acc.equity == 10000.0
        assert acc.currency == "USD"
        client.disconnect()

    def test_get_symbol_info(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        sym = client.get_symbol_info("EURUSD")
        assert sym.name == "EURUSD"
        assert sym.digits == 5
        assert sym.spread_pips == 1.2
        assert sym.pip_size == 0.0001
        client.disconnect()

    def test_get_candles(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        candles = client.get_candles("EURUSD", Timeframe.M5, 2)
        assert len(candles) == 2
        assert candles[0].open == 1.0850
        assert candles[1].close == 1.0860
        client.disconnect()

    def test_place_order_success(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        res = client.place_order(
            symbol="EURUSD",
            direction=Signal.BUY,
            volume=0.1,
            sl_price=1.0830,
            tp_price=1.0890,
            magic=100101,
        )
        assert res.success is True
        assert res.ticket == 7891234
        assert res.retcode == 10009
        client.disconnect()

    def test_place_order_rejected(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        with pytest.raises(BrokerExecutionError) as exc_info:
            client.place_order(
                symbol="EURUSD",
                direction=Signal.BUY,
                volume=999.0,  # triggers mock server rejection
                sl_price=1.0830,
                tp_price=1.0890,
            )
        assert "Invalid volume" in str(exc_info.value)
        client.disconnect()

    def test_close_position(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        res = client.close_position(7891234)
        assert res.success is True
        assert res.ticket == 7891234
        client.disconnect()

    def test_get_open_positions(self, mock_server):
        client = SocketBrokerClient(host="127.0.0.1", port=mock_server.port, timeout=2.0)
        client.connect()
        positions = client.get_open_positions(magic=100101)
        assert len(positions) == 1
        assert positions[0].ticket == 7891234
        assert positions[0].direction == Signal.BUY
        assert positions[0].profit == 5.0
        client.disconnect()
