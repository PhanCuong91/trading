"""Unit tests for the OrderManager."""

from datetime import datetime

import pytest

from forex_signals.data.models import Candle, Order, OrderStatus, Signal
from forex_signals.orders.manager import OrderManager


@pytest.fixture
def manager():
    """OrderManager with 20 SL pips, 40 TP pips, standard pip_value."""
    return OrderManager(sl_pips=20, tp_pips=40, pip_value=0.0001)


class TestCreateOrder:
    """Tests for OrderManager.create_order."""

    def test_buy_order_sl_below_entry(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        assert order.stop_loss < order.entry_price

    def test_buy_order_tp_above_entry(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        assert order.take_profit > order.entry_price

    def test_buy_order_sl_distance(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        expected_sl = 1.1000 - 20 * 0.0001
        assert order.stop_loss == pytest.approx(expected_sl)

    def test_buy_order_tp_distance(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        expected_tp = 1.1000 + 40 * 0.0001
        assert order.take_profit == pytest.approx(expected_tp)

    def test_sell_order_sl_above_entry(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        assert order.stop_loss > order.entry_price

    def test_sell_order_tp_below_entry(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        assert order.take_profit < order.entry_price

    def test_sell_order_sl_distance(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        expected_sl = 1.1000 + 20 * 0.0001
        assert order.stop_loss == pytest.approx(expected_sl)

    def test_sell_order_tp_distance(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        expected_tp = 1.1000 - 40 * 0.0001
        assert order.take_profit == pytest.approx(expected_tp)

    def test_order_starts_open(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        assert order.status == OrderStatus.OPEN

    def test_order_has_no_exit_initially(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        assert order.exit_time is None
        assert order.exit_price is None
        assert order.pnl is None

    def test_neutral_direction_raises(self, manager):
        with pytest.raises(ValueError, match="NEUTRAL"):
            manager.create_order(Signal.NEUTRAL, 1.1000, datetime(2024, 1, 1))


class TestUpdateOrder:
    """Tests for OrderManager.update_order."""

    def _make_candle(self, low, high, timestamp=None):
        """Helper to create a candle with specified low/high."""
        ts = timestamp or datetime(2024, 1, 2)
        return Candle(
            timestamp=ts,
            open=(low + high) / 2,
            high=high,
            low=low,
            close=(low + high) / 2,
            volume=100.0,
        )

    def test_buy_order_untouched_when_price_in_range(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        # Candle stays between SL and TP
        candle = self._make_candle(low=1.0985, high=1.1035)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.OPEN

    def test_buy_order_closes_at_sl(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        # SL is at 1.0980, candle low hits it
        candle = self._make_candle(low=1.0975, high=1.1020)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.CLOSED_SL
        assert updated.exit_price == pytest.approx(order.stop_loss)

    def test_buy_order_closes_at_tp(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        # TP is at 1.1040, candle high reaches it
        candle = self._make_candle(low=1.0985, high=1.1045)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.CLOSED_TP
        assert updated.exit_price == pytest.approx(order.take_profit)

    def test_buy_order_sl_precedence_when_both_hit(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        # Both SL and TP hit in same candle
        candle = self._make_candle(low=1.0970, high=1.1050)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.CLOSED_SL

    def test_sell_order_closes_at_sl(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        # SL is at 1.1020, candle high hits it
        candle = self._make_candle(low=1.0970, high=1.1025)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.CLOSED_SL
        assert updated.exit_price == pytest.approx(order.stop_loss)

    def test_sell_order_closes_at_tp(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        # TP is at 1.0960, candle low hits it
        candle = self._make_candle(low=1.0955, high=1.1015)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.CLOSED_TP
        assert updated.exit_price == pytest.approx(order.take_profit)

    def test_sell_order_sl_precedence_when_both_hit(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        # Both SL and TP hit
        candle = self._make_candle(low=1.0950, high=1.1030)
        updated = manager.update_order(order, candle)
        assert updated.status == OrderStatus.CLOSED_SL

    def test_closed_order_not_modified(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        # Close it first
        candle1 = self._make_candle(low=1.0970, high=1.1020)
        order = manager.update_order(order, candle1)
        assert order.status == OrderStatus.CLOSED_SL

        # Now try to update again - should be unchanged
        candle2 = self._make_candle(low=1.0950, high=1.1050, timestamp=datetime(2024, 1, 3))
        order = manager.update_order(order, candle2)
        assert order.status == OrderStatus.CLOSED_SL
        assert order.exit_time == candle1.timestamp

    def test_buy_pnl_positive_on_tp(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        candle = self._make_candle(low=1.0985, high=1.1045)
        updated = manager.update_order(order, candle)
        assert updated.pnl is not None
        assert updated.pnl > 0

    def test_buy_pnl_negative_on_sl(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        candle = self._make_candle(low=1.0975, high=1.1020)
        updated = manager.update_order(order, candle)
        assert updated.pnl is not None
        assert updated.pnl < 0

    def test_sell_pnl_positive_on_tp(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        candle = self._make_candle(low=1.0955, high=1.1015)
        updated = manager.update_order(order, candle)
        assert updated.pnl is not None
        assert updated.pnl > 0

    def test_sell_pnl_negative_on_sl(self, manager):
        order = manager.create_order(Signal.SELL, 1.1000, datetime(2024, 1, 1))
        candle = self._make_candle(low=1.0970, high=1.1025)
        updated = manager.update_order(order, candle)
        assert updated.pnl is not None
        assert updated.pnl < 0

    def test_exit_time_matches_candle_timestamp(self, manager):
        order = manager.create_order(Signal.BUY, 1.1000, datetime(2024, 1, 1))
        ts = datetime(2024, 1, 5, 14, 30)
        candle = self._make_candle(low=1.0970, high=1.1020, timestamp=ts)
        updated = manager.update_order(order, candle)
        assert updated.exit_time == ts
