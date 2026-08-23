"""Configuration loading and validation for the forex trading signal system."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
class CsvExportConfig:
    """Configuration for optional CSV export of downloaded candle data."""

    enabled: bool
    output_dir: str


@dataclass(frozen=True)
class AutoTuneConfig:
    """Configuration for optional auto-tuning of backtesting parameters."""

    enabled: bool = False
    train_split: float = 0.7
    consensus_threshold_values: List[int] = field(default_factory=lambda: [2, 3, 4, 5])
    strategy_param_values: Dict[str, Dict[str, List[Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class Mt5Config:
    """Configuration for MetaTrader 5 live trading via TCP Socket Bridge (Method A)."""

    enabled: bool = False
    mock: bool = False
    host: str = "127.0.0.1"
    port: int = 5555
    symbol: str = "EURUSD"
    lot_size: float = 0.1
    magic_number: int = 100101
    max_spread_pips: float = 2.5
    deviation_points: int = 10
    poll_interval_seconds: float = 5.0
    timeout_seconds: float = 5.0


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
    csv_export: CsvExportConfig = field(
        default_factory=lambda: CsvExportConfig(enabled=False, output_dir="data")
    )
    auto_tune: AutoTuneConfig = field(default_factory=AutoTuneConfig)
    mt5: Mt5Config = field(default_factory=Mt5Config)


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


def _validate_csv_export(value: Any) -> CsvExportConfig:
    """Validate the csv_export configuration section."""
    if not isinstance(value, dict):
        raise ConfigError("csv_export must be a mapping with 'enabled' and 'output_dir'")

    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError(f"csv_export.enabled must be a boolean, got: {enabled!r}")

    output_dir = value.get("output_dir", "data")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise ConfigError("csv_export.output_dir must be a non-empty string")

    return CsvExportConfig(enabled=enabled, output_dir=output_dir)


def _validate_auto_tune(value: Any) -> AutoTuneConfig:
    """Validate the auto_tune configuration section."""
    if not isinstance(value, dict):
        raise ConfigError("auto_tune must be a mapping with 'enabled' and optional tuning settings")

    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError(f"auto_tune.enabled must be a boolean, got: {enabled!r}")

    train_split = value.get("train_split", 0.7)
    try:
        train_split_value = float(train_split)
    except (TypeError, ValueError):
        raise ConfigError(f"auto_tune.train_split must be a number, got: {train_split!r}")
    if not 0 < train_split_value < 1:
        raise ConfigError(
            f"auto_tune.train_split must be between 0 and 1, got: {train_split_value}"
        )

    threshold_values = value.get("consensus_threshold_values", [2, 3, 4, 5])
    if not isinstance(threshold_values, list) or not threshold_values:
        raise ConfigError("auto_tune.consensus_threshold_values must be a non-empty list")
    validated_thresholds: List[int] = []
    for item in threshold_values:
        try:
            threshold = int(item)
        except (TypeError, ValueError):
            raise ConfigError(
                f"auto_tune.consensus_threshold_values must contain integers, got: {item!r}"
            )
        if threshold < 1:
            raise ConfigError(
                f"auto_tune.consensus_threshold_values must be positive, got: {threshold}"
            )
        validated_thresholds.append(threshold)

    strategy_param_values = value.get("strategy_param_values", {})
    if not isinstance(strategy_param_values, dict):
        raise ConfigError("auto_tune.strategy_param_values must be a mapping")

    return AutoTuneConfig(
        enabled=enabled,
        train_split=train_split_value,
        consensus_threshold_values=validated_thresholds,
        strategy_param_values=strategy_param_values,
    )


def _validate_mt5_config(value: Any) -> Mt5Config:
    """Validate the mt5 configuration section."""
    if not isinstance(value, dict):
        raise ConfigError("mt5 must be a mapping with MT5 configuration settings")

    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError(f"mt5.enabled must be a boolean, got: {enabled!r}")

    mock = value.get("mock", False)
    if not isinstance(mock, bool):
        raise ConfigError(f"mt5.mock must be a boolean, got: {mock!r}")

    host = value.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host.strip():
        raise ConfigError("mt5.host must be a non-empty string")

    port = value.get("port", 5555)
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        raise ConfigError(f"mt5.port must be an integer, got: {port!r}")
    if not 1 <= port_int <= 65535:
        raise ConfigError(f"mt5.port must be between 1 and 65535, got: {port_int}")

    symbol = value.get("symbol", "EURUSD")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ConfigError("mt5.symbol must be a non-empty string")

    lot_size = _validate_positive_number(value.get("lot_size", 0.1), "mt5.lot_size")
    magic = int(value.get("magic_number", 100101))
    max_spread = _validate_positive_number(value.get("max_spread_pips", 2.5), "mt5.max_spread_pips")
    deviation = int(value.get("deviation_points", 10))
    poll_int = _validate_positive_number(value.get("poll_interval_seconds", 5.0), "mt5.poll_interval_seconds")
    timeout = _validate_positive_number(value.get("timeout_seconds", 5.0), "mt5.timeout_seconds")

    return Mt5Config(
        enabled=enabled,
        mock=mock,
        host=host,
        port=port_int,
        symbol=symbol,
        lot_size=lot_size,
        magic_number=magic,
        max_spread_pips=max_spread,
        deviation_points=deviation,
        poll_interval_seconds=poll_int,
        timeout_seconds=timeout,
    )



def load_config(
    config_path: Optional[str] = None,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    sl_pips: Optional[float] = None,
    tp_pips: Optional[float] = None,
    csv_export_enabled: Optional[bool] = None,
    csv_export_dir: Optional[str] = None,
    auto_tune_enabled: Optional[bool] = None,
) -> AppConfig:
    """Load and validate configuration from a YAML file with optional CLI overrides.

    Args:
        config_path: Path to the YAML config file. Defaults to 'config.yaml' in the
                     current working directory.
        pair: CLI override for the trading pair.
        timeframe: CLI override for the timeframe (enum name, e.g. 'M5').
        sl_pips: CLI override for stop-loss pips.
        tp_pips: CLI override for take-profit pips.
        csv_export_enabled: CLI override for whether CSV export is enabled.
        csv_export_dir: CLI override for the CSV export output directory.
                        Providing this implies csv export is enabled unless
                        csv_export_enabled explicitly disables it.
        auto_tune_enabled: CLI override for whether auto-tuning is enabled.

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

    # Validate csv_export section, applying CLI overrides
    csv_export_section = raw.get("csv_export", {})
    if not isinstance(csv_export_section, dict):
        raise ConfigError("csv_export must be a mapping with 'enabled' and 'output_dir'")

    csv_export_raw = dict(csv_export_section)
    if csv_export_dir is not None:
        csv_export_raw["output_dir"] = csv_export_dir
        csv_export_raw["enabled"] = True
    if csv_export_enabled is not None:
        csv_export_raw["enabled"] = csv_export_enabled

    validated_csv_export = _validate_csv_export(csv_export_raw)

    auto_tune_section = raw.get("auto_tune", {})
    if not isinstance(auto_tune_section, dict):
        raise ConfigError("auto_tune must be a mapping with 'enabled' and optional tuning settings")

    auto_tune_raw = dict(auto_tune_section)
    if auto_tune_enabled is not None:
        auto_tune_raw["enabled"] = auto_tune_enabled

    validated_auto_tune = _validate_auto_tune(auto_tune_raw)

    mt5_section = raw.get("mt5", {})
    if not isinstance(mt5_section, dict):
        raise ConfigError("mt5 must be a mapping with MT5 configuration settings")
    validated_mt5 = _validate_mt5_config(mt5_section)

    return AppConfig(
        pair=validated_pair,
        timeframe=validated_timeframe,
        sl_pips=validated_sl_pips,
        tp_pips=validated_tp_pips,
        consensus_threshold=validated_threshold,
        strategies=validated_strategies,
        backtest=validated_backtest,
        csv_export=validated_csv_export,
        auto_tune=validated_auto_tune,
        mt5=validated_mt5,
    )



def _require_field(data: dict, field_name: str, section: str = "") -> None:
    """Check that a required field exists in the config dictionary."""
    if field_name not in data:
        prefix = f"{section}." if section else ""
        raise ConfigError(f"Missing required configuration field: {prefix}{field_name}")
