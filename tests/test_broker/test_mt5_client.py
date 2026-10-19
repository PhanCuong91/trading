"""Unit tests for MT5BrokerClient using mocked MetaTrader5 module."""

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from forex_signals.broker.models import (
    AccountInfo,
    BrokerConnectionError,
    BrokerError,
    BrokerExecutionError,
    Position,
    SymbolInfo,
    TradeExecutionResult,
)
from forex_signals.broker.mt5_client import MT5BrokerClient
from forex_signals.data.models import Candle, Signal, Timeframe


@dataclass
class FakeAccountInfo:
    login: int = 123456
    server: str = "MetaQuotes-Demo"
    currency: str = "USD"
    balance: float = 10000.0
    equity: float = 10250.0
    margin: float = 200.0
    margin_free: float = 10050.0
    leverage: int = 100


@dataclass
class FakeSymbolInfo:
    name: str = "EURUSD"
    digits: int = 5
    point: float = 0.00001
    spread: int = 12
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    trade_stops_level: int = 10
    trade_contract_size: float = 100000.0


@dataclass
class FakeTick:
    ask: float = 1.08550
    bid: float = 1.08538


@dataclass
class FakeOrderResult:
    retcode: int = 10009
    order: int = 7891234
    deal: int = 7891234
    price: float = 1.08550
    volume: float = 0.1
    comment: str = "Done"


@dataclass
class FakePosition:
    ticket: int = 7891234
    symbol: str = "EURUSD"
    type: int = 0  # 0: BUY, 1: SELL
    volume: float = 0.1
    price_open: float = 1.08500
    sl: float = 1.08300
    tp: float = 1.08900
    time: int = 1783680000
    price_current: float = 1.08550
    profit: float = 5.0
    magic: int = 100101
    comment: str = "bot"


@pytest.fixture
def mock_mt5():
    """Create a fully-mocked MetaTrader5 module."""
    m = MagicMock()
    m.initialize.return_value = True
    m.login.return_value = True
    m.shutdown.return_value = None
    m.last_error.return_value = (1, "No error")
    m.terminal_info.return_value = MagicMock(connected=True)
    m.account_info.return_value = FakeAccountInfo()
    m.symbol_info.return_value = FakeSymbolInfo()
    m.symbol_info_tick.return_value = FakeTick()
    m.symbol_select.return_value = True
    m.order_send.return_value = FakeOrderResult()
    m.positions_get.return_value = (FakePosition(),)
    m.copy_rates_from_pos.return_value = [
        {"time": 1783680000, "open": 1.0850, "high": 1.0860, "low": 1.0845, "close": 1.0855, "tick_volume": 120}
    ]
    # Constants
    m.TRADE_ACTION_DEAL = 1
    m.TRADE_RETCODE_DONE = 10009
    m.TRADE_RETCODE_INVALID_FILL = 10030
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.ORDER_TIME_GTC = 0
    m.ORDER_FILLING_IOC = 1
    m.ORDER_FILLING_FOK = 0
    m.TIMEFRAME_M1 = 1
    m.TIMEFRAME_M5 = 5
    m.TIMEFRAME_M15 = 15
    m.TIMEFRAME_M30 = 30
    m.TIMEFRAME_H1 = 60
    m.TIMEFRAME_H4 = 240
    m.TIMEFRAME_D1 = 1440
    return m


class TestMT5BrokerClient:
    """Tests for direct MT5 client operations."""

    def test_missing_mt5_module_raises(self):
        client = MT5BrokerClient(mt5_module=None)
        client._mt5 = None
        with pytest.raises(BrokerConnectionError, match="MetaTrader5 Python package is not available"):
            client.connect()

    def test_connect_success(self, mock_mt5):
        client = MT5BrokerClient(
            path="/path/to/terminal64.exe",
            login=123456,
            password="pwd",
            server="DemoServer",
            timeout=3000,
            mt5_module=mock_mt5,
        )
        assert client.connect() is True
        assert client.is_connected() is True
        mock_mt5.initialize.assert_called_once()
        mock_mt5.login.assert_called_once_with(login=123456, password="pwd", server="DemoServer")

    def test_connect_initialize_failure(self, mock_mt5):
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (-1, "Terminal not found")
        client = MT5BrokerClient(mt5_module=mock_mt5)
        with pytest.raises(BrokerConnectionError, match="Failed to initialize MetaTrader 5"):
            client.connect()

    def test_connect_login_failure(self, mock_mt5):
        mock_mt5.login.return_value = False
        mock_mt5.last_error.return_value = (-2, "Invalid credentials")
        client = MT5BrokerClient(login=123, password="p", server="s", mt5_module=mock_mt5)
        with pytest.raises(BrokerConnectionError, match="Failed to log into MT5 account"):
            client.connect()

    def test_disconnect(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        client.disconnect()
        assert client.is_connected() is False
        mock_mt5.shutdown.assert_called_once()

    def test_get_account_info(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        acc = client.get_account_info()
        assert isinstance(acc, AccountInfo)
        assert acc.login == 123456
        assert acc.balance == 10000.0
        assert acc.free_margin == 10050.0

    def test_get_symbol_info(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        info = client.get_symbol_info("EURUSD")
        assert isinstance(info, SymbolInfo)
        assert info.name == "EURUSD"
        assert info.digits == 5
        assert info.spread_points == 12
        assert info.spread_pips == 1.2
        assert info.min_lot == 0.01

    def test_get_symbol_info_not_found(self, mock_mt5):
        mock_mt5.symbol_info.return_value = None
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        with pytest.raises(BrokerError, match="Failed to fetch symbol info"):
            client.get_symbol_info("UNKNOWN")

    def test_get_candles(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        candles = client.get_candles("EURUSD", Timeframe.M5, 1)
        assert len(candles) == 1
        assert isinstance(candles[0], Candle)
        assert candles[0].open == 1.0850
        assert candles[0].close == 1.0855
        assert candles[0].volume == 120

    def test_place_order_buy_success(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        res = client.place_order(
            symbol="EURUSD",
            direction=Signal.BUY,
            volume=0.1,
            sl_price=1.0830,
            tp_price=1.0890,
            deviation=10,
            magic=100101,
        )
        assert isinstance(res, TradeExecutionResult)
        assert res.success is True
        assert res.ticket == 7891234
        assert res.retcode == 10009

    def test_place_order_sell_success(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        res = client.place_order(
            symbol="EURUSD",
            direction=Signal.SELL,
            volume=0.2,
            sl_price=1.0870,
            tp_price=1.0810,
            deviation=10,
            magic=100101,
        )
        assert isinstance(res, TradeExecutionResult)
        assert res.success is True

    def test_place_order_rejected(self, mock_mt5):
        mock_mt5.order_send.return_value = MagicMock(retcode=10013, comment="Invalid price")
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        with pytest.raises(BrokerExecutionError, match="Order rejected by MT5"):
            client.place_order(
                symbol="EURUSD",
                direction=Signal.BUY,
                volume=0.1,
                sl_price=1.0830,
                tp_price=1.0890,
            )

    def test_close_position_success(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        res = client.close_position(ticket=7891234)
        assert isinstance(res, TradeExecutionResult)
        assert res.success is True
        assert res.ticket == 7891234

    def test_close_position_not_found(self, mock_mt5):
        mock_mt5.positions_get.return_value = ()
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        with pytest.raises(BrokerExecutionError, match="Position ticket 9999 not found"):
            client.close_position(ticket=9999)

    def test_get_open_positions(self, mock_mt5):
        client = MT5BrokerClient(mt5_module=mock_mt5)
        client.connect()
        positions = client.get_open_positions(magic=100101)
        assert len(positions) == 1
        assert isinstance(positions[0], Position)
        assert positions[0].ticket == 7891234
        assert positions[0].direction == Signal.BUY
        assert positions[0].magic == 100101

