"""Unit tests for broker data models and exceptions."""

from datetime import datetime

import pytest

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
from forex_signals.data.models import Signal


class TestBrokerModels:
    """Test broker dataclasses and enums."""

    def test_broker_type_enum(self):
        assert BrokerType.MT5.value == "mt5"
        assert BrokerType.MOCK.value == "mock"

    def test_account_info_creation(self):
        acc = AccountInfo(
            login=123456,
            server="MetaQuotes-Demo",
            currency="USD",
            balance=10000.0,
            equity=10250.0,
            margin=200.0,
            free_margin=10050.0,
            leverage=100,
        )
        assert acc.login == 123456
        assert acc.balance == 10000.0
        assert acc.equity == 10250.0
        assert acc.free_margin == 10050.0
        assert acc.leverage == 100

    def test_symbol_info_creation(self):
        sym = SymbolInfo(
            name="EURUSD",
            digits=5,
            point=0.00001,
            pip_size=0.0001,
            spread_points=12,
            spread_pips=1.2,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            stop_level_points=10,
            trade_contract_size=100000.0,
        )
        assert sym.name == "EURUSD"
        assert sym.digits == 5
        assert sym.pip_size == 0.0001
        assert sym.spread_pips == 1.2
        assert sym.stop_level_points == 10

    def test_position_creation(self):
        now = datetime(2026, 8, 19, 12, 0, 0)
        pos = Position(
            ticket=7891234,
            symbol="EURUSD",
            direction=Signal.BUY,
            volume=0.1,
            open_price=1.08500,
            stop_loss=1.08300,
            take_profit=1.08900,
            open_time=now,
            current_price=1.08600,
            profit=10.0,
            magic=100101,
            comment="test_buy",
        )
        assert pos.ticket == 7891234
        assert pos.direction == Signal.BUY
        assert pos.profit == 10.0
        assert pos.magic == 100101

    def test_trade_execution_result_creation(self):
        now = datetime(2026, 8, 19, 12, 0, 0)
        res = TradeExecutionResult(
            success=True,
            retcode=10009,
            ticket=7891234,
            order_id="7891234",
            price=1.08500,
            volume=0.1,
            timestamp=now,
            error_message="",
        )
        assert res.success is True
        assert res.retcode == 10009
        assert res.ticket == 7891234

    def test_exceptions_hierarchy(self):
        assert issubclass(BrokerConnectionError, BrokerError)
        assert issubclass(BrokerExecutionError, BrokerError)
        assert issubclass(SpreadExceededError, BrokerError)
