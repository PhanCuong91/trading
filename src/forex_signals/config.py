"""Configuration loading and validation for the forex trading signal system."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from forex_signals.data.models import Timeframe


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for a single strategy."""

    params: Dict[str, Any]


@dataclass(frozen=True)
class BacktestDateConfig:
    """Backtest date range configuration."""

    start_date: datetime
    end_date: datetime


@dataclass(frozen=True)
class AppConfig:
    """Complete application configuration."""

    pair: str
    timeframe: Timeframe
    sl_pips: float
    tp_pips: float
    consensus_threshold: int
    strategies: Dict[str, StrategyConfig]
    backtest: BacktestDateConfig


# Mapping from config file timeframe string (enum name) to Timeframe enum
_VALID_TIMEFRAME_NAMES = {tf.name for tf in Timeframe}


def _validate_positive_number(value: Any, field_name: str) -> float:
    """Validate that a value is a positive number."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{field_name} must be a number, got: {value!r}")
    if num <= 0:
        raise ConfigError(f"{field_name} must be positive, got: {num}")
    return num


def _validate_timeframe(value: Any) -> Timeframe:
    """Validate and convert a timeframe string to Timeframe enum."""
    if not isinstance(value, str):
        raise ConfigError(f"timeframe must be a string, got: {value!r}")
    if value not in _VALID_TIMEFRAME_NAMES:
        raise ConfigError(
            f"Invalid timeframe '{value}'. "
            f"Valid values: {', '.join(sorted(_VALID_TIMEFRAME_NAMES))}"
        )
    return Timeframe[value]


def _validate_date(value: Any, field_name: str) -> datetime:
    """Validate and parse a date string (YYYY-MM-DD format)."""
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a date string (YYYY-MM-DD), got: {value!r}")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ConfigError(
            f"{field_name} must be a valid date in YYYY-MM-DD format, got: '{value}'"
        )


def _validate_consensus_threshold(value: Any) -> int:
    """Validate the consensus threshold."""
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"consensus_threshold must be an integer, got: {value!r}")
    if threshold < 1:
        raise ConfigError(f"consensus_threshold must be at least 1, got: {threshold}")
    return threshold


def load_config(
    config_path: Optional[str] = None,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    sl_pips: Optional[float] = None,
    tp_pips: Optional[float] = None,
) -> AppConfig:
    """Load and validate configuration from a YAML file with optional CLI overrides.

    Args:
        config_path: Path to the YAML config file. Defaults to 'config.yaml' in the
                     current working directory.
        pair: CLI override for the trading pair.
        timeframe: CLI override for the timeframe (enum name, e.g. 'M5').
        sl_pips: CLI override for stop-loss pips.
        tp_pips: CLI override for take-profit pips.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigError: If the config file cannot be loaded or contains invalid values.
    """
    # Determine config file path
    if config_path is None:
        config_path = "config.yaml"

    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    # Load YAML
    try:
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML configuration: {e}")

    if not isinstance(raw, dict):
        raise ConfigError("Configuration file must contain a YAML mapping (dictionary)")

    # Apply CLI overrides (None means "use config file value")
    if pair is not None:
        raw["pair"] = pair
    if timeframe is not None:
        raw["timeframe"] = timeframe
    if sl_pips is not None:
        raw["sl_pips"] = sl_pips
    if tp_pips is not None:
        raw["tp_pips"] = tp_pips

    # Validate required top-level fields
    _require_field(raw, "pair")
    _require_field(raw, "timeframe")
    _require_field(raw, "sl_pips")
    _require_field(raw, "tp_pips")
    _require_field(raw, "consensus_threshold")

    # Validate individual fields
    validated_pair = raw["pair"]
    if not isinstance(validated_pair, str) or not validated_pair.strip():
        raise ConfigError("pair must be a non-empty string")

    validated_timeframe = _validate_timeframe(raw["timeframe"])
    validated_sl_pips = _validate_positive_number(raw["sl_pips"], "sl_pips")
    validated_tp_pips = _validate_positive_number(raw["tp_pips"], "tp_pips")
    validated_threshold = _validate_consensus_threshold(raw["consensus_threshold"])

    # Validate strategies section
    strategies_raw = raw.get("strategies", {})
    if not isinstance(strategies_raw, dict):
        raise ConfigError("strategies must be a mapping of strategy names to parameters")

    validated_strategies: Dict[str, StrategyConfig] = {}
    for name, params in strategies_raw.items():
        if not isinstance(params, dict):
            raise ConfigError(f"Strategy '{name}' parameters must be a mapping, got: {type(params).__name__}")
        validated_strategies[name] = StrategyConfig(params=params)

    # Validate backtest section
    backtest_raw = raw.get("backtest", {})
    if not isinstance(backtest_raw, dict):
        raise ConfigError("backtest must be a mapping with start_date and end_date")

    _require_field(backtest_raw, "start_date", section="backtest")
    _require_field(backtest_raw, "end_date", section="backtest")

    start_date = _validate_date(backtest_raw["start_date"], "backtest.start_date")
    end_date = _validate_date(backtest_raw["end_date"], "backtest.end_date")

    if end_date <= start_date:
        raise ConfigError(
            f"backtest.end_date ({backtest_raw['end_date']}) must be after "
            f"backtest.start_date ({backtest_raw['start_date']})"
        )

    validated_backtest = BacktestDateConfig(start_date=start_date, end_date=end_date)

    return AppConfig(
        pair=validated_pair,
        timeframe=validated_timeframe,
        sl_pips=validated_sl_pips,
        tp_pips=validated_tp_pips,
        consensus_threshold=validated_threshold,
        strategies=validated_strategies,
        backtest=validated_backtest,
    )


def _require_field(data: dict, field_name: str, section: str = "") -> None:
    """Check that a required field exists in the config dictionary."""
    if field_name not in data:
        prefix = f"{section}." if section else ""
        raise ConfigError(f"Missing required configuration field: {prefix}{field_name}")
