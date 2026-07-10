"""Trading strategies."""

from forex_signals.strategies.base import Strategy
from forex_signals.strategies.bollinger import BollingerBandsStrategy
from forex_signals.strategies.macd import MACDStrategy
from forex_signals.strategies.moving_average import MovingAverageCrossoverStrategy
from forex_signals.strategies.rsi import RSIStrategy
from forex_signals.strategies.smi import SMIStrategy

__all__ = [
    "Strategy",
    "BollingerBandsStrategy",
    "SMIStrategy",
    "MovingAverageCrossoverStrategy",
    "RSIStrategy",
    "MACDStrategy",
]
