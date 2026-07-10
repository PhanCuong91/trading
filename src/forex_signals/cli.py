"""CLI entry point for the forex trading signal system."""

import sys
from typing import Optional

import click

from forex_signals.backtest.engine import BacktestEngine
from forex_signals.config import ConfigError, load_config
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
def backtest(
    config_path: Optional[str],
    pair: Optional[str],
    timeframe: Optional[str],
    sl_pips: Optional[float],
    tp_pips: Optional[float],
    start_date: Optional[str],
    end_date: Optional[str],
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

    # Download data
    click.echo(
        f"Downloading {config.pair} data ({config.timeframe.name}) "
        f"from {backtest_start.date()} to {backtest_end.date()}..."
    )
    downloader = YahooDataDownloader()
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

    # Run backtest
    engine = BacktestEngine(
        strategies=strategies,
        consensus=consensus,
        order_manager=order_manager,
    )
    result = engine.run(candles)

    # Display results
    _print_results(result)
