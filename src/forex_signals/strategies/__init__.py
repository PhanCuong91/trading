"""Trading strategies."""

from forex_signals.strategies.base import Strategy
from forex_signals.strategies.smi import SMIStrategy

__all__ = ["Strategy", "SMIStrategy"]
