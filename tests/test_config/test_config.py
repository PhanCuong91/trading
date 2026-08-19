"""Tests for configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from forex_signals.config import AppConfig, AutoTuneConfig, ConfigError, load_config
from forex_signals.data.models import Timeframe


@pytest.fixture
def valid_config_data():
    """Return a valid configuration dictionary."""
    return {
        "pair": "EURUSD=X",
        "timeframe": "M5",
        "sl_pips": 20,
        "tp_pips": 40,
        "consensus_threshold": 4,
        "strategies": {
            "smi": {"period": 14, "smooth_period": 3},
            "moving_average": {"fast_period": 10, "slow_period": 50},
            "rsi": {"period": 14, "overbought": 70, "oversold": 30},
            "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            "bollinger": {"period": 20, "std_dev": 2.0},
        },
        "backtest": {
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
    }


@pytest.fixture
def config_file(valid_config_data, tmp_path):
    """Write a valid config to a temp file and return its path."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(valid_config_data, f)
    return str(config_path)


class TestLoadConfigHappyPath:
    """Tests for successful configuration loading."""

    def test_loads_valid_config(self, config_file):
        config = load_config(config_path=config_file)
        assert config.pair == "EURUSD=X"
        assert config.timeframe == Timeframe.M5
        assert config.sl_pips == 20.0
        assert config.tp_pips == 40.0
        assert config.consensus_threshold == 4

    def test_loads_strategies(self, config_file):
        config = load_config(config_path=config_file)
        assert "smi" in config.strategies
        assert config.strategies["smi"].params == {"period": 14, "smooth_period": 3}
        assert "bollinger" in config.strategies
        assert config.strategies["bollinger"].params == {"period": 20, "std_dev": 2.0}

    def test_loads_backtest_dates(self, config_file):
        config = load_config(config_path=config_file)
        assert config.backtest.start_date.year == 2024
        assert config.backtest.start_date.month == 1
        assert config.backtest.start_date.day == 1
        assert config.backtest.end_date.year == 2024
        assert config.backtest.end_date.month == 12
        assert config.backtest.end_date.day == 31

    def test_all_valid_timeframes(self, valid_config_data, tmp_path):
        for tf_name in ["M5", "M15", "H1", "H4", "D1"]:
            valid_config_data["timeframe"] = tf_name
            config_path = tmp_path / f"config_{tf_name}.yaml"
            with open(config_path, "w") as f:
                yaml.dump(valid_config_data, f)
            config = load_config(config_path=str(config_path))
            assert config.timeframe == Timeframe[tf_name]


class TestCLIOverrides:
    """Tests for CLI parameter overrides."""

    def test_override_pair(self, config_file):
        config = load_config(config_path=config_file, pair="GBPUSD=X")
        assert config.pair == "GBPUSD=X"

    def test_override_timeframe(self, config_file):
        config = load_config(config_path=config_file, timeframe="H1")
        assert config.timeframe == Timeframe.H1

    def test_override_sl_pips(self, config_file):
        config = load_config(config_path=config_file, sl_pips=30.0)
        assert config.sl_pips == 30.0

    def test_override_tp_pips(self, config_file):
        config = load_config(config_path=config_file, tp_pips=60.0)
        assert config.tp_pips == 60.0

    def test_none_overrides_use_file_values(self, config_file):
        config = load_config(
            config_path=config_file, pair=None, timeframe=None, sl_pips=None, tp_pips=None
        )
        assert config.pair == "EURUSD=X"
        assert config.timeframe == Timeframe.M5
        assert config.sl_pips == 20.0
        assert config.tp_pips == 40.0


class TestValidationErrors:
    """Tests for configuration validation errors."""

    def test_missing_config_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(config_path=str(tmp_path / "nonexistent.yaml"))

    def test_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("{ invalid yaml: [")
        with pytest.raises(ConfigError, match="Failed to parse YAML"):
            load_config(config_path=str(bad_yaml))

    def test_non_dict_yaml(self, tmp_path):
        scalar_yaml = tmp_path / "scalar.yaml"
        scalar_yaml.write_text("just a string")
        with pytest.raises(ConfigError, match="must contain a YAML mapping"):
            load_config(config_path=str(scalar_yaml))

    def test_missing_pair(self, valid_config_data, tmp_path):
        del valid_config_data["pair"]
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="Missing required.*pair"):
            load_config(config_path=str(path))

    def test_empty_pair(self, valid_config_data, tmp_path):
        valid_config_data["pair"] = "   "
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="pair must be a non-empty string"):
            load_config(config_path=str(path))

    def test_invalid_timeframe(self, valid_config_data, tmp_path):
        valid_config_data["timeframe"] = "INVALID"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="Invalid timeframe"):
            load_config(config_path=str(path))

    def test_negative_sl_pips(self, valid_config_data, tmp_path):
        valid_config_data["sl_pips"] = -5
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="sl_pips must be positive"):
            load_config(config_path=str(path))

    def test_zero_tp_pips(self, valid_config_data, tmp_path):
        valid_config_data["tp_pips"] = 0
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="tp_pips must be positive"):
            load_config(config_path=str(path))

    def test_non_numeric_sl_pips(self, valid_config_data, tmp_path):
        valid_config_data["sl_pips"] = "abc"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="sl_pips must be a number"):
            load_config(config_path=str(path))

    def test_invalid_start_date(self, valid_config_data, tmp_path):
        valid_config_data["backtest"]["start_date"] = "not-a-date"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="backtest.start_date must be a valid date"):
            load_config(config_path=str(path))

    def test_end_date_before_start_date(self, valid_config_data, tmp_path):
        valid_config_data["backtest"]["start_date"] = "2024-12-31"
        valid_config_data["backtest"]["end_date"] = "2024-01-01"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="end_date.*must be after.*start_date"):
            load_config(config_path=str(path))

    def test_invalid_consensus_threshold(self, valid_config_data, tmp_path):
        valid_config_data["consensus_threshold"] = 0
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="consensus_threshold must be at least 1"):
            load_config(config_path=str(path))

    def test_strategies_not_dict(self, valid_config_data, tmp_path):
        valid_config_data["strategies"] = "not a dict"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="strategies must be a mapping"):
            load_config(config_path=str(path))

    def test_strategy_params_not_dict(self, valid_config_data, tmp_path):
        valid_config_data["strategies"]["smi"] = "not a dict"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="Strategy 'smi' parameters must be a mapping"):
            load_config(config_path=str(path))


class TestDefaultConfigFile:
    """Test loading from the project's default config.yaml."""

    def test_loads_project_config(self):
        """Load the actual project config.yaml to ensure it's valid."""
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config.yaml"
        if config_path.exists():
            config = load_config(config_path=str(config_path))
            assert config.pair == "EURUSD=X"
            assert config.timeframe == Timeframe.M5


class TestAutoTuneConfig:
    """Tests for the optional auto_tune configuration section."""

    def test_defaults_when_section_missing(self, valid_config_data, tmp_path):
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        config = load_config(config_path=str(path))
        assert config.auto_tune.enabled is False
        assert config.auto_tune.train_split == 0.7
        assert config.auto_tune.consensus_threshold_values == [2, 3, 4, 5]

    def test_loads_explicit_auto_tune_section(self, valid_config_data, tmp_path):
        valid_config_data["auto_tune"] = {
            "enabled": True,
            "train_split": 0.6,
            "consensus_threshold_values": [3, 4],
            "strategy_param_values": {
                "smi": {"period": [7, 14]},
            },
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        config = load_config(config_path=str(path))
        assert config.auto_tune.enabled is True
        assert config.auto_tune.train_split == 0.6
        assert config.auto_tune.consensus_threshold_values == [3, 4]
        assert config.auto_tune.strategy_param_values["smi"]["period"] == [7, 14]

    def test_auto_tune_section_not_dict_raises(self, valid_config_data, tmp_path):
        valid_config_data["auto_tune"] = "not a dict"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="auto_tune must be a mapping"):
            load_config(config_path=str(path))


class TestCsvExportConfig:
    """Tests for the optional csv_export configuration section."""

    def test_defaults_when_section_missing(self, valid_config_data, tmp_path):
        """csv_export defaults to disabled with output_dir 'data' when omitted."""
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        config = load_config(config_path=str(path))
        assert config.csv_export.enabled is False
        assert config.csv_export.output_dir == "data"

    def test_loads_explicit_csv_export_section(self, valid_config_data, tmp_path):
        valid_config_data["csv_export"] = {"enabled": True, "output_dir": "exports"}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        config = load_config(config_path=str(path))
        assert config.csv_export.enabled is True
        assert config.csv_export.output_dir == "exports"

    def test_csv_export_not_dict_raises(self, valid_config_data, tmp_path):
        valid_config_data["csv_export"] = "not a dict"
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="csv_export must be a mapping"):
            load_config(config_path=str(path))

    def test_csv_export_enabled_not_bool_raises(self, valid_config_data, tmp_path):
        valid_config_data["csv_export"] = {"enabled": "yes"}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="csv_export.enabled must be a boolean"):
            load_config(config_path=str(path))

    def test_csv_export_output_dir_empty_raises(self, valid_config_data, tmp_path):
        valid_config_data["csv_export"] = {"output_dir": "   "}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(valid_config_data, f)
        with pytest.raises(ConfigError, match="csv_export.output_dir must be a non-empty string"):
            load_config(config_path=str(path))

    def test_cli_override_csv_export_enabled(self, config_file):
        config = load_config(config_path=config_file, csv_export_enabled=True)
        assert config.csv_export.enabled is True
        assert config.csv_export.output_dir == "data"

    def test_cli_override_csv_dir_implies_enabled(self, config_file):
        config = load_config(config_path=config_file, csv_export_dir="custom_dir")
        assert config.csv_export.enabled is True
        assert config.csv_export.output_dir == "custom_dir"

    def test_cli_override_no_save_csv_wins_over_dir(self, config_file):
        """Explicit --no-save-csv should override the implicit enable from --csv-dir."""
        config = load_config(
            config_path=config_file, csv_export_enabled=False, csv_export_dir="custom_dir"
        )
        assert config.csv_export.enabled is False
        assert config.csv_export.output_dir == "custom_dir"
