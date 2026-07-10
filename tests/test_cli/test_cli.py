"""Tests for the CLI entry point."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from forex_signals.cli import _build_strategies, _print_results, main
from forex_signals.config import AppConfig, BacktestDateConfig, ConfigError, StrategyConfig
from forex_signals.data.downloader import DataDownloadError
from forex_signals.data.models import BacktestResult, Timeframe


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_config():
    return AppConfig(
        pair="EURUSD=X",
        timeframe=Timeframe.M5,
        sl_pips=20.0,
        tp_pips=40.0,
        consensus_threshold=4,
        strategies={
            "smi": StrategyConfig(params={"period": 14, "smooth_period": 3}),
            "moving_average": StrategyConfig(params={"fast_period": 10, "slow_period": 50}),
            "rsi": StrategyConfig(params={"period": 14, "overbought": 70, "oversold": 30}),
            "macd": StrategyConfig(params={"fast_period": 12, "slow_period": 26, "signal_period": 9}),
            "bollinger": StrategyConfig(params={"period": 20, "std_dev": 2.0}),
        },
        backtest=BacktestDateConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        ),
    )


@pytest.fixture
def sample_result():
    return BacktestResult(
        trades=[],
        win_rate=0.55,
        total_pnl=0.0123,
        max_drawdown=0.005,
        sharpe_ratio=1.25,
        profit_factor=1.8,
        avg_trade_duration_seconds=3600.0,
        num_trades=10,
    )


class TestMainGroup:
    def test_help_shows_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "backtest" in result.output

    def test_backtest_help_shows_options(self, runner):
        result = runner.invoke(main, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "--pair" in result.output
        assert "--timeframe" in result.output
        assert "--sl-pips" in result.output
        assert "--tp-pips" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--config" in result.output


class TestBacktestCommand:
    @patch("forex_signals.cli.load_config")
    def test_config_error_exits_with_message(self, mock_load_config, runner):
        mock_load_config.side_effect = ConfigError("bad config")
        result = runner.invoke(main, ["backtest"])
        assert result.exit_code == 1
        assert "Configuration error: bad config" in result.output

    @patch("forex_signals.cli.YahooDataDownloader")
    @patch("forex_signals.cli.load_config")
    def test_download_error_exits_with_message(
        self, mock_load_config, mock_downloader_cls, runner, sample_config
    ):
        mock_load_config.return_value = sample_config
        mock_downloader = MagicMock()
        mock_downloader.download.side_effect = DataDownloadError("network timeout")
        mock_downloader_cls.return_value = mock_downloader

        result = runner.invoke(main, ["backtest"])
        assert result.exit_code == 1
        assert "Data download error: network timeout" in result.output

    @patch("forex_signals.cli.BacktestEngine")
    @patch("forex_signals.cli.YahooDataDownloader")
    @patch("forex_signals.cli.load_config")
    def test_successful_backtest_prints_results(
        self, mock_load_config, mock_downloader_cls, mock_engine_cls, runner, sample_config, sample_result
    ):
        mock_load_config.return_value = sample_config
        mock_downloader = MagicMock()
        mock_downloader.download.return_value = [MagicMock() for _ in range(100)]
        mock_downloader_cls.return_value = mock_downloader
        mock_engine = MagicMock()
        mock_engine.run.return_value = sample_result
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(main, ["backtest"])
        assert result.exit_code == 0
        assert "BACKTEST RESULTS" in result.output
        assert "Total Trades" in result.output
        assert "Win Rate" in result.output
        assert "55.00%" in result.output
        assert "10" in result.output

    @patch("forex_signals.cli.load_config")
    def test_invalid_start_date_exits(self, mock_load_config, runner, sample_config):
        mock_load_config.return_value = sample_config
        result = runner.invoke(main, ["backtest", "--start-date", "not-a-date"])
        assert result.exit_code == 1
        assert "Invalid start-date format" in result.output

    @patch("forex_signals.cli.load_config")
    def test_invalid_end_date_exits(self, mock_load_config, runner, sample_config):
        mock_load_config.return_value = sample_config
        result = runner.invoke(main, ["backtest", "--end-date", "bad"])
        assert result.exit_code == 1
        assert "Invalid end-date format" in result.output


class TestBuildStrategies:
    def test_builds_all_five_strategies(self, sample_config):
        strategies = _build_strategies(sample_config)
        assert len(strategies) == 5

    def test_unknown_strategy_skipped(self, sample_config):
        # Create config with an unknown strategy
        config = AppConfig(
            pair=sample_config.pair,
            timeframe=sample_config.timeframe,
            sl_pips=sample_config.sl_pips,
            tp_pips=sample_config.tp_pips,
            consensus_threshold=sample_config.consensus_threshold,
            strategies={"unknown_strategy": StrategyConfig(params={})},
            backtest=sample_config.backtest,
        )
        strategies = _build_strategies(config)
        assert len(strategies) == 0

    def test_strategy_names_match(self, sample_config):
        strategies = _build_strategies(sample_config)
        names = {s.name for s in strategies}
        assert "SMI" in names
        assert "MA Crossover" in names
        assert "RSI" in names
        assert "MACD" in names
        assert "Bollinger Bands" in names


class TestPrintResults:
    def test_prints_all_metrics(self, sample_result, capsys):
        _print_results(sample_result)
        captured = capsys.readouterr()
        assert "BACKTEST RESULTS" in captured.out
        assert "Total Trades" in captured.out
        assert "Win Rate" in captured.out
        assert "Total PnL" in captured.out
        assert "Max Drawdown" in captured.out
        assert "Sharpe Ratio" in captured.out
        assert "Profit Factor" in captured.out
        assert "Avg Trade Duration" in captured.out
