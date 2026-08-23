"""Live trading execution engine coordinating broker, strategies, consensus, and risk controls."""

import logging
import math
import time
from datetime import datetime
from typing import List, Optional, Tuple

from forex_signals.broker.base import Broker
from forex_signals.broker.models import (
    BrokerError,
    BrokerExecutionError,
    Position,
    SpreadExceededError,
    SymbolInfo,
    TradeExecutionResult,
)
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import Candle, Signal, StrategySignal, Timeframe
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies.base import Strategy

logger = logging.getLogger(__name__)


def quantize_lot_size(raw_lot: float, spec: SymbolInfo) -> float:
    """Clamp lot size to [min_lot, max_lot] and round to nearest lot_step multiple.

    Args:
        raw_lot: Requested volume in lots.
        spec: Symbol specification from broker.

    Returns:
        Quantized volume rounded to step precision.
    """
    if raw_lot <= spec.min_lot:
        return spec.min_lot
    if raw_lot >= spec.max_lot:
        return spec.max_lot

    if spec.lot_step <= 0:
        return round(raw_lot, 2)

    # Determine decimal places from lot_step and min_lot
    step_str = f"{spec.lot_step:.8f}".rstrip("0")
    min_str = f"{spec.min_lot:.8f}".rstrip("0")
    step_dec = len(step_str.split(".")[1]) if "." in step_str else 2
    min_dec = len(min_str.split(".")[1]) if "." in min_str else 2
    decimals = max(step_dec, min_dec)

    steps = round((raw_lot - spec.min_lot) / spec.lot_step)
    quantized = spec.min_lot + steps * spec.lot_step
    quantized = max(spec.min_lot, min(quantized, spec.max_lot))
    return round(quantized, decimals)



def adjust_sl_tp_for_stoplevel(
    direction: Signal,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    spec: SymbolInfo,
) -> Tuple[float, float]:
    """Ensure stop-loss and take-profit prices respect broker's minimum stop level.

    Args:
        direction: Signal.BUY or Signal.SELL.
        entry_price: Market entry price.
        sl_price: Initial calculated stop-loss price.
        tp_price: Initial calculated take-profit price.
        spec: Symbol specification with stop_level_points and point size.

    Returns:
        Tuple of (adjusted_sl, adjusted_tp) rounded to symbol digits.
    """
    min_dist = spec.stop_level_points * spec.point

    if direction == Signal.BUY:
        # SL must be at least min_dist below entry
        if entry_price - sl_price < min_dist:
            sl_price = entry_price - min_dist
        # TP must be at least min_dist above entry
        if tp_price - entry_price < min_dist:
            tp_price = entry_price + min_dist
    elif direction == Signal.SELL:
        # SL must be at least min_dist above entry
        if sl_price - entry_price < min_dist:
            sl_price = entry_price + min_dist
        # TP must be at least min_dist below entry
        if entry_price - tp_price < min_dist:
            tp_price = entry_price - min_dist

    return round(sl_price, spec.digits), round(tp_price, spec.digits)


class LiveTradingEngine:
    """Orchestrates live trading loops, risk checks, and MT5 order execution."""

    def __init__(
        self,
        broker: Broker,
        strategies: List[Strategy],
        consensus: ConsensusEngine,
        order_manager: OrderManager,
        symbol: str = "EURUSD",
        timeframe: Timeframe = Timeframe.M5,
        lot_size: float = 0.1,
        magic_number: int = 100101,
        max_spread_pips: float = 2.5,
        poll_interval_seconds: float = 5.0,
    ):
        """Initialize the live trading engine.

        Args:
            broker: Connected Broker instance.
            strategies: List of technical analysis strategies.
            consensus: ConsensusEngine instance.
            order_manager: OrderManager configured with SL/TP pips.
            symbol: Symbol to trade (e.g. 'EURUSD').
            timeframe: Candle timeframe.
            lot_size: Base order volume in lots.
            magic_number: Unique bot magic identifier.
            max_spread_pips: Max allowable spread in pips before skipping.
            poll_interval_seconds: Polling sleep interval in seconds.
        """
        self.broker = broker
        self.strategies = strategies
        self.consensus = consensus
        self.order_manager = order_manager
        self.symbol = symbol
        self.timeframe = timeframe
        self.lot_size = lot_size
        self.magic_number = magic_number
        self.max_spread_pips = max_spread_pips
        self.poll_interval_seconds = poll_interval_seconds
        self._running = False

    def step(self) -> Optional[TradeExecutionResult]:
        """Perform a single cycle: data query -> strategy check -> consensus -> order execution.

        Returns:
            TradeExecutionResult if a trade action was executed, else None.
        """
        # 1. Fetch Symbol Specification
        spec = self.broker.get_symbol_info(self.symbol)

        # 2. Spread Guardrail Filter
        if spec.spread_pips > self.max_spread_pips:
            logger.warning(
                "Live spread (%.2f pips) exceeds max allowable spread (%.2f pips). Skipping trade check.",
                spec.spread_pips,
                self.max_spread_pips,
            )
            return None

        # 3. Query Candle History
        max_min_candles = max((s.min_candles for s in self.strategies), default=50) + 10
        candles = self.broker.get_candles(self.symbol, self.timeframe, count=max_min_candles)
        if not candles:
            logger.warning("No candle data received for %s.", self.symbol)
            return None

        # 4. Generate Strategy Signals
        now = datetime.now()
        signals = [
            StrategySignal(strategy_name=s.name, signal=s.generate_signal(candles), timestamp=now)
            for s in self.strategies
        ]

        # 5. Evaluate Consensus
        consensus_sig = self.consensus.evaluate(signals)
        logger.debug("Consensus signal for %s: %s", self.symbol, consensus_sig.value)

        # 6. Check Open Positions
        open_positions = self.broker.get_open_positions(magic=self.magic_number)
        matching_positions = [p for p in open_positions if p.symbol == self.symbol]

        # 7. Position Lifecycle & Trade Execution
        if matching_positions:
            current_pos = matching_positions[0]
            # If opposite signal occurs, close existing position
            if (
                (current_pos.direction == Signal.BUY and consensus_sig == Signal.SELL)
                or (current_pos.direction == Signal.SELL and consensus_sig == Signal.BUY)
            ):
                logger.info(
                    "Opposite consensus signal (%s) detected. Closing position ticket %d.",
                    consensus_sig.value,
                    current_pos.ticket,
                )
                return self.broker.close_position(current_pos.ticket)

            # If same direction or neutral, maintain position
            return None

        # If no position is open and consensus triggers BUY or SELL
        if consensus_sig in (Signal.BUY, Signal.SELL):
            entry_price = candles[-1].close
            order = self.order_manager.create_order(consensus_sig, entry_price, now)

            # Adjust SL/TP for broker minimum stop level and digits
            adj_sl, adj_tp = adjust_sl_tp_for_stoplevel(
                direction=consensus_sig,
                entry_price=entry_price,
                sl_price=order.stop_loss,
                tp_price=order.take_profit,
                spec=spec,
            )

            # Quantize volume
            volume = quantize_lot_size(self.lot_size, spec)

            logger.info(
                "Consensus %s triggered for %s. Placing order: vol=%.2f, entry=%.5f, SL=%.5f, TP=%.5f",
                consensus_sig.value,
                self.symbol,
                volume,
                entry_price,
                adj_sl,
                adj_tp,
            )

            return self.broker.place_order(
                symbol=self.symbol,
                direction=consensus_sig,
                volume=volume,
                sl_price=adj_sl,
                tp_price=adj_tp,
                deviation=10,
                magic=self.magic_number,
                comment=f"forex_bot_{consensus_sig.value.lower()}",
            )

        return None

    def run(self, max_iterations: Optional[int] = None) -> None:
        """Run the live trading loop continuously.

        Args:
            max_iterations: Optional loop iteration limit (useful for testing).
        """
        if not self.broker.is_connected():
            logger.info("Connecting broker client...")
            self.broker.connect()

        self._running = True
        logger.info(
            "Live trading engine started for %s (%s). Polling every %.1fs.",
            self.symbol,
            self.timeframe.name,
            self.poll_interval_seconds,
        )

        iteration = 0
        try:
            while self._running:
                try:
                    self.step()
                except Exception as e:
                    logger.error("Error during live trading step: %s", e, exc_info=True)

                iteration += 1
                if max_iterations is not None and iteration >= max_iterations:
                    break

                time.sleep(self.poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Live trading interrupted by user.")
        finally:
            self._running = False
            logger.info("Live trading engine stopped.")

    def stop(self) -> None:
        """Stop the running loop."""
        self._running = False
