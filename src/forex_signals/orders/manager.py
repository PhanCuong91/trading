"""Order lifecycle management."""

from datetime import datetime

from forex_signals.data.models import Candle, Order, OrderStatus, Signal


class OrderManager:
    """Creates and manages order lifecycle."""

    def __init__(self, sl_pips: float, tp_pips: float, pip_value: float = 0.0001):
        """
        Initialize OrderManager with stop-loss and take-profit configuration.

        Args:
            sl_pips: Stop-loss distance in pips.
            tp_pips: Take-profit distance in pips.
            pip_value: Value of one pip (default 0.0001 for most forex pairs).
        """
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.pip_value = pip_value

    def create_order(
        self, direction: Signal, entry_price: float, entry_time: datetime
    ) -> Order:
        """
        Create an order with calculated SL and TP prices.

        For BUY: SL = entry - sl_pips * pip_value, TP = entry + tp_pips * pip_value
        For SELL: SL = entry + sl_pips * pip_value, TP = entry - tp_pips * pip_value

        Args:
            direction: Signal.BUY or Signal.SELL
            entry_price: The price at which the order is entered.
            entry_time: Timestamp of order entry.

        Returns:
            A new Order instance with OPEN status.

        Raises:
            ValueError: If direction is Signal.NEUTRAL.
        """
        if direction == Signal.NEUTRAL:
            raise ValueError("Cannot create an order with NEUTRAL direction.")

        sl_distance = self.sl_pips * self.pip_value
        tp_distance = self.tp_pips * self.pip_value

        if direction == Signal.BUY:
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:  # SELL
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        return Order(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=entry_time,
        )

    def update_order(self, order: Order, candle: Candle) -> Order:
        """
        Check if the given candle triggers SL or TP.

        SL takes precedence when both SL and TP are hit in the same candle
        (worst-case assumption).

        A BUY order closes at SL if candle.low <= stop_loss
        and closes at TP if candle.high >= take_profit.

        A SELL order closes at SL if candle.high >= stop_loss
        and closes at TP if candle.low <= take_profit.

        Once closed, an order's status never changes again.

        Args:
            order: The order to check.
            candle: The current candle to check against.

        Returns:
            The (possibly updated) order. If closed, exit_time, exit_price,
            status, and pnl are set.
        """
        # Already closed orders are unchanged
        if order.status != OrderStatus.OPEN:
            return order

        sl_hit = False
        tp_hit = False

        if order.direction == Signal.BUY:
            sl_hit = candle.low <= order.stop_loss
            tp_hit = candle.high >= order.take_profit
        else:  # SELL
            sl_hit = candle.high >= order.stop_loss
            tp_hit = candle.low <= order.take_profit

        # SL takes precedence (worst-case assumption)
        if sl_hit:
            order.exit_price = order.stop_loss
            order.exit_time = candle.timestamp
            order.status = OrderStatus.CLOSED_SL
        elif tp_hit:
            order.exit_price = order.take_profit
            order.exit_time = candle.timestamp
            order.status = OrderStatus.CLOSED_TP

        # Calculate PnL on close
        if order.status != OrderStatus.OPEN and order.exit_price is not None:
            if order.direction == Signal.BUY:
                order.pnl = order.exit_price - order.entry_price
            else:  # SELL
                order.pnl = order.entry_price - order.exit_price

        return order
