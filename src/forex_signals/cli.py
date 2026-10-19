"""CLI entry point for the forex trading signal system."""

import os
import sys
from typing import Optional

import click

from forex_signals.backtest.engine import BacktestEngine
from forex_signals.config import ConfigError, load_config
from forex_signals.backtest.tuner import AutoTuningEngine
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.downloader import DataDownloadError, YahooDataDownloader
from forex_signals.data.models import BacktestResult
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies import (
    BollingerBandsStrategy,
    MACDStrategy,
    MovingAverageCrossoverStrategy,
    RSIStrategy,
    SMIStrategy,
)


def _build_strategies(config):
    """Instantiate all strategies from config.

    Args:
        config: AppConfig with strategies dict mapping name -> StrategyConfig.

    Returns:
        List of Strategy instances.
    """
    strategy_map = {
        "smi": lambda params: SMIStrategy(
            period=params.get("period", 14),
            smooth_period=params.get("smooth_period", 3),
        ),
        "moving_average": lambda params: MovingAverageCrossoverStrategy(
            fast_period=params.get("fast_period", 10),
            slow_period=params.get("slow_period", 50),
        ),
        "rsi": lambda params: RSIStrategy(
            period=params.get("period", 14),
            overbought=params.get("overbought", 70),
            oversold=params.get("oversold", 30),
        ),
        "macd": lambda params: MACDStrategy(
            fast_period=params.get("fast_period", 12),
            slow_period=params.get("slow_period", 26),
            signal_period=params.get("signal_period", 9),
        ),
        "bollinger": lambda params: BollingerBandsStrategy(
            period=params.get("period", 20),
            std_dev=params.get("std_dev", 2.0),
        ),
    }

    strategies = []
    for name, strategy_config in config.strategies.items():
        factory = strategy_map.get(name)
        if factory is None:
            click.echo(f"Warning: Unknown strategy '{name}', skipping.", err=True)
            continue
        strategies.append(factory(strategy_config.params))

    return strategies


def _build_strategies_from_params(config, tuned_params):
    """Instantiate strategies from a tuned parameter mapping."""
    strategy_map = {
        "smi": lambda params: SMIStrategy(
            period=params.get("period", 14),
            smooth_period=params.get("smooth_period", 3),
        ),
        "moving_average": lambda params: MovingAverageCrossoverStrategy(
            fast_period=params.get("fast_period", 10),
            slow_period=params.get("slow_period", 50),
        ),
        "rsi": lambda params: RSIStrategy(
            period=params.get("period", 14),
            overbought=params.get("overbought", 70),
            oversold=params.get("oversold", 30),
        ),
        "macd": lambda params: MACDStrategy(
            fast_period=params.get("fast_period", 12),
            slow_period=params.get("slow_period", 26),
            signal_period=params.get("signal_period", 9),
        ),
        "bollinger": lambda params: BollingerBandsStrategy(
            period=params.get("period", 20),
            std_dev=params.get("std_dev", 2.0),
        ),
    }

    strategies = []
    for name, strategy_config in config.strategies.items():
        factory = strategy_map.get(name)
        if factory is None:
            click.echo(f"Warning: Unknown strategy '{name}', skipping.", err=True)
            continue
        params = tuned_params.get(name, {})
        strategies.append(factory(params))

    return strategies


def _print_results(result: BacktestResult) -> None:
    """Pretty-print backtest results as a formatted metrics table.

    Args:
        result: BacktestResult containing all computed metrics.
    """
    click.echo("")
    click.echo("=" * 50)
    click.echo("         BACKTEST RESULTS")
    click.echo("=" * 50)
    click.echo("")

    metrics = [
        ("Total Trades", f"{result.num_trades}"),
        ("Win Rate", f"{result.win_rate:.2%}"),
        ("Total PnL", f"{result.total_pnl:.6f}"),
        ("Max Drawdown", f"{result.max_drawdown:.6f}"),
        ("Sharpe Ratio", f"{result.sharpe_ratio:.4f}"),
        ("Profit Factor", f"{result.profit_factor:.4f}"),
        ("Avg Trade Duration", f"{result.avg_trade_duration_seconds:.0f}s"),
    ]

    label_width = max(len(label) for label, _ in metrics)
    for label, value in metrics:
        click.echo(f"  {label:<{label_width}}  │  {value}")

    click.echo("")
    click.echo("=" * 50)


@click.group()
def main():
    """Forex trading signal system CLI."""
    pass


@main.command()
@click.option("--config", "config_path", default=None, help="Path to YAML config file.")
@click.option("--pair", default=None, help="Forex pair (e.g. EURUSD=X).")
@click.option("--timeframe", default=None, help="Candle timeframe (M5, M15, H1, H4, D1).")
@click.option("--sl-pips", type=float, default=None, help="Stop-loss in pips.")
@click.option("--tp-pips", type=float, default=None, help="Take-profit in pips.")
@click.option("--start-date", default=None, help="Backtest start date (YYYY-MM-DD).")
@click.option("--end-date", default=None, help="Backtest end date (YYYY-MM-DD).")
@click.option(
    "--save-csv/--no-save-csv",
    "save_csv",
    default=None,
    help="Enable/disable exporting downloaded candles to a CSV file.",
)
@click.option("--csv-dir", default=None, help="Directory to write the CSV export into.")
@click.option("--auto-tune", is_flag=True, default=False, help="Automatically tune consensus threshold and strategy parameters before the final backtest.")
def backtest(
    config_path: Optional[str],
    pair: Optional[str],
    timeframe: Optional[str],
    sl_pips: Optional[float],
    tp_pips: Optional[float],
    start_date: Optional[str],
    end_date: Optional[str],
    save_csv: Optional[bool],
    csv_dir: Optional[str],
    auto_tune: bool,
) -> None:
    """Run a backtest with the configured strategies."""
    # Load configuration with CLI overrides
    try:
        config = load_config(
            config_path=config_path,
            pair=pair,
            timeframe=timeframe,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            csv_export_enabled=save_csv,
            csv_export_dir=csv_dir,
            auto_tune_enabled=auto_tune,
        )
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)

    # Apply start/end date overrides if provided
    backtest_start = config.backtest.start_date
    backtest_end = config.backtest.end_date

    if start_date is not None:
        from datetime import datetime

        try:
            backtest_start = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            click.echo(
                f"Invalid start-date format: '{start_date}'. Use YYYY-MM-DD.",
                err=True,
            )
            sys.exit(1)

    if end_date is not None:
        from datetime import datetime

        try:
            backtest_end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            click.echo(
                f"Invalid end-date format: '{end_date}'. Use YYYY-MM-DD.",
                err=True,
            )
            sys.exit(1)

    # Build strategies
    strategies = _build_strategies(config)
    if not strategies:
        click.echo("Error: No valid strategies configured.", err=True)
        sys.exit(1)

    # Create consensus engine and order manager
    consensus = ConsensusEngine(threshold=config.consensus_threshold)
    order_manager = OrderManager(sl_pips=config.sl_pips, tp_pips=config.tp_pips)

    downloader = YahooDataDownloader()

    # If CSV export is enabled and a matching cached CSV file already exists,
    # load candles from it and skip the download entirely.
    cached_csv_path = None
    if config.csv_export.enabled:
        cached_csv_path = downloader.get_csv_path(
            pair=config.pair,
            timeframe=config.timeframe,
            start=backtest_start,
            end=backtest_end,
            output_dir=config.csv_export.output_dir,
        )

    if cached_csv_path and os.path.exists(cached_csv_path):
        click.echo(f"Found cached CSV file, skipping download: {cached_csv_path}")
        try:
            candles = downloader.load_from_csv(cached_csv_path)
        except DataDownloadError as e:
            click.echo(f"Data download error: {e}", err=True)
            sys.exit(1)
        click.echo(f"Loaded {len(candles)} candles from CSV.")
    else:
        # Download data
        click.echo(
            f"Downloading {config.pair} data ({config.timeframe.name}) "
            f"from {backtest_start.date()} to {backtest_end.date()}..."
        )
        try:
            candles = downloader.download(
                pair=config.pair,
                timeframe=config.timeframe,
                start=backtest_start,
                end=backtest_end,
            )
        except DataDownloadError as e:
            click.echo(f"Data download error: {e}", err=True)
            sys.exit(1)

        click.echo(f"Downloaded {len(candles)} candles.")

        # Export to CSV if enabled
        if config.csv_export.enabled:
            try:
                csv_path = downloader.export_to_csv(
                    candles,
                    pair=config.pair,
                    timeframe=config.timeframe,
                    start=backtest_start,
                    end=backtest_end,
                    output_dir=config.csv_export.output_dir,
                )
                click.echo(f"Candles exported to CSV: {csv_path}")
            except OSError as e:
                click.echo(f"Warning: failed to export candles to CSV: {e}", err=True)

    if config.auto_tune.enabled:
        tuning_output_path = None
        if config.csv_export.enabled:
            tuning_output_path = os.path.join(
                config.csv_export.output_dir,
                f"auto_tune_results_{config.pair.replace('/', '_').replace('=', '')}.csv",
            )

        click.echo("Auto-tuning is running. Please wait while the system evaluates candidate configurations...")
        if tuning_output_path and os.path.exists(tuning_output_path):
            click.echo(f"Found existing tuning results file: {tuning_output_path}")
        tuner = AutoTuningEngine(
            strategies=strategies,
            order_manager=order_manager,
            train_split=config.auto_tune.train_split,
            consensus_threshold_values=config.auto_tune.consensus_threshold_values,
            strategy_param_values=config.auto_tune.strategy_param_values,
            output_path=tuning_output_path,
        )
        tuning_result = tuner.tune(candles)
        click.echo(
            f"Auto-tuning selected consensus_threshold={tuning_result.consensus_threshold} and strategy params={tuning_result.strategy_params}"
        )
        strategies = _build_strategies_from_params(config, tuning_result.strategy_params)
        consensus = ConsensusEngine(threshold=tuning_result.consensus_threshold)

    # Run backtest
    engine = BacktestEngine(
        strategies=strategies,
        consensus=consensus,
        order_manager=order_manager,
    )
    result = engine.run(candles)

    # Display results
    _print_results(result)


@main.command()
@click.option("--config", "config_path", default=None, help="Path to YAML config file.")
@click.option("--pair", "--symbol", "symbol", default=None, help="Forex pair / symbol (e.g. EURUSD).")
@click.option("--mock/--no-mock", "mock", default=None, help="Use mock broker instead of live MT5 terminal.")
@click.option("--path", default=None, help="Path to MT5 terminal64.exe executable.")
@click.option("--login", type=int, default=None, help="MT5 account login number.")
@click.option("--password", default=None, help="MT5 account password.")
@click.option("--server", default=None, help="MT5 broker server name.")
@click.option("--lot-size", type=float, default=None, help="Order lot size (e.g. 0.1).")
@click.option("--magic-number", type=int, default=None, help="Magic number for bot orders.")
@click.option("--max-spread", type=float, default=None, help="Max allowable spread in pips.")
@click.option("--poll-interval", type=float, default=None, help="Polling interval in seconds.")
@click.option("--max-iterations", type=int, default=None, help="Stop after N iterations (for testing).")
def live(
    config_path: Optional[str],
    symbol: Optional[str],
    mock: Optional[bool],
    path: Optional[str],
    login: Optional[int],
    password: Optional[str],
    server: Optional[str],
    lot_size: Optional[float],
    magic_number: Optional[int],
    max_spread: Optional[float],
    poll_interval: Optional[float],
    max_iterations: Optional[int],
) -> None:
    """Run live trading via MetaTrader 5 Direct Python module or Mock."""
    try:
        config = load_config(config_path=config_path)
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)

    # Determine runtime options
    is_mock = mock if mock is not None else config.mt5.mock
    mt5_path = path or config.mt5.path
    mt5_login = login if login is not None else config.mt5.login
    mt5_password = password or config.mt5.password
    mt5_server = server or config.mt5.server
    trade_symbol = symbol or config.mt5.symbol
    trade_lot = lot_size if lot_size is not None else config.mt5.lot_size
    bot_magic = magic_number if magic_number is not None else config.mt5.magic_number
    max_spread_pips = max_spread if max_spread is not None else config.mt5.max_spread_pips
    poll_sec = poll_interval if poll_interval is not None else config.mt5.poll_interval_seconds

    # Instantiate Broker
    if is_mock:
        from forex_signals.broker.mock import MockBrokerClient

        click.echo("Starting live trading engine with MOCK broker simulation...")
        broker = MockBrokerClient()
    else:
        from forex_signals.broker.mt5_client import MT5BrokerClient

        click.echo(f"Connecting to MetaTrader 5 terminal for symbol {trade_symbol}...")
        broker = MT5BrokerClient(
            path=mt5_path,
            login=mt5_login,
            password=mt5_password,
            server=mt5_server,
            timeout=config.mt5.timeout_ms,
        )

    try:
        broker.connect()
        acc = broker.get_account_info()
        click.echo(
            f"Connected to broker. Account: {acc.login} | Server: {acc.server} | "
            f"Balance: {acc.balance:.2f} {acc.currency} | Equity: {acc.equity:.2f} {acc.currency}"
        )
    except Exception as e:
        click.echo(f"Failed to connect to broker: {e}", err=True)
        sys.exit(1)

    # Build strategies and consensus
    strategies = _build_strategies(config)
    consensus = ConsensusEngine(threshold=config.consensus_threshold)
    order_manager = OrderManager(
        sl_pips=config.sl_pips,
        tp_pips=config.tp_pips,
    )

    from forex_signals.broker.live_runner import LiveTradingEngine

    engine = LiveTradingEngine(
        broker=broker,
        strategies=strategies,
        consensus=consensus,
        order_manager=order_manager,
        symbol=trade_symbol,
        timeframe=config.timeframe,
        lot_size=trade_lot,
        magic_number=bot_magic,
        max_spread_pips=max_spread_pips,
        poll_interval_seconds=poll_sec,
    )

    try:
        engine.run(max_iterations=max_iterations)
    except KeyboardInterrupt:
        click.echo("\nLive trading terminated by user.")
    finally:
        broker.disconnect()
        click.echo("Broker disconnected. Goodbye!")

