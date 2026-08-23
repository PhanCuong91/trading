"""Unit tests for MockBrokerClient."""

from datetime import datetime

import pytest

from forex_signals.broker.mock import MockBrokerClient
from forex_signals.broker.models import BrokerConnectionError, BrokerExecutionError
from forex_signals.data.models import Candle, Signal, Timeframe


@pytest.fixture
def mock_broker():
    """Connected MockBrokerClient fixture."""
    broker = MockBrokerClient(initial_balance=10000.0)
    broker.connect()
    return broker


class TestMockBroker:
    """Tests for MockBrokerClient."""

    def test_connection_lifecycle(self):
        broker = MockBrokerClient()
        assert not broker.is_connected()
        assert broker.connect() is True
        assert broker.is_connected() is True
        broker.disconnect()
        assert not broker.is_connected()

    def test_not_connected_raises(self):
        broker = MockBrokerClient()
        with pytest.raises(BrokerConnectionError):
            broker.get_account_info()
        with pytest.raises(BrokerConnectionError):
            broker.get_symbol_info("EURUSD")
        with pytest.raises(BrokerConnectionError):
            broker.get_candles("EURUSD", Timeframe.M5, 10)
        with pytest.raises(BrokerConnectionError):
            broker.place_order("EURUSD", Signal.BUY, 0.1, 1.0800, 1.0900)
        with pytest.raises(BrokerConnectionError):
            broker.close_position(12345)
        with pytest.raises(BrokerConnectionError):
            broker.get_open_positions()

    def test_get_account_info(self, mock_broker):
        info = mock_broker.get_account_info()
        assert info.balance == 10000.0
        assert info.equity == 10000.0
        assert info.free_margin == 10000.0
        assert info.currency == "USD"
        assert info.leverage == 100

    def test_get_symbol_info(self, mock_broker):
        info = mock_broker.get_symbol_info("EURUSD")
        assert info.name == "EURUSD"
        assert info.digits == 5
        assert info.pip_size == 0.0001
        assert info.min_lot == 0.01

    def test_place_and_close_buy_order(self, mock_broker):
        mock_broker.set_price("EURUSD", 1.08500)
        res = mock_broker.place_order(
            symbol="EURUSD",
            direction=Signal.BUY,
            volume=0.1,
            sl_price=1.08300,
            tp_price=1.08900,
            magic=100101,
            comment="test_buy",
        )
        assert res.success is True
        assert res.ticket is not None
        ticket = res.ticket

        positions = mock_broker.get_open_positions(magic=100101)
        assert len(positions) == 1
        assert positions[0].ticket == ticket
        assert positions[0].direction == Signal.BUY
        assert positions[0].volume == 0.1

        # Price goes up by 10 pips (0.0010) -> profit = 0.0010 * 0.1 * 100,000 = $10
        mock_broker.set_price("EURUSD", 1.08600)
        acc_info = mock_broker.get_account_info()
        assert acc_info.equity == pytest.approx(10010.0)

        # Close position
        close_res = mock_broker.close_position(ticket)
        assert close_res.success is True
        assert len(mock_broker.get_open_positions()) == 0
        assert mock_broker.get_account_info().balance == pytest.approx(10010.0)

    def test_place_invalid_volume(self, mock_broker):
        with pytest.raises(BrokerExecutionError):
            mock_broker.place_order("EURUSD", Signal.BUY, 0.0001, 1.0800, 1.0900)
        with pytest.raises(BrokerExecutionError):
            mock_broker.place_order("EURUSD", Signal.BUY, 1000.0, 1.0800, 1.0900)

    def test_close_nonexistent_position_raises(self, mock_broker):
        with pytest.raises(BrokerExecutionError):
            mock_broker.close_position(9999999)

    def test_get_candles(self, mock_broker):
        now = datetime.now()
        candles = [
            Candle(now, 1.0800, 1.0850, 1.0790, 1.0840, 100),
            Candle(now, 1.0840, 1.0860, 1.0830, 1.0850, 120),
        ]
        mock_broker.set_candles("EURUSD", candles)
        result = mock_broker.get_candles("EURUSD", Timeframe.M5, 1)
        assert len(result) == 1
        assert result[0].close == 1.0850
