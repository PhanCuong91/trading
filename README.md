# Forex Trading Signal System

A Python application that downloads forex candlestick data from Yahoo Finance, runs five independent technical-analysis strategies, and generates a **BUY**/**SELL** signal only when at least 4 of the 5 strategies agree (consensus). Signals are turned into simulated orders with configurable stop-loss/take-profit, and the whole pipeline can be backtested against historical data with standard performance metrics.

```
Data Source (Yahoo Finance) → Strategy Engine (5 strategies) → Consensus → Order Manager → Backtest Engine
```

## Features

- **Data download** — OHLC candles from Yahoo Finance via `yfinance`, with retry/backoff and gap detection.
- **5 trading strategies** (each returns `BUY` / `SELL` / `NEUTRAL`):
  - SMI (Stochastic Momentum Index)
  - Moving Average crossover (fast/slow)
  - RSI (Relative Strength Index)
  - MACD (Moving Average Convergence Divergence)
  - Bollinger Bands
- **Consensus engine** — equal-weighted vote; a trade signal requires at least `consensus_threshold` (default 4) of 5 strategies to agree.
- **Order management** — computes stop-loss/take-profit prices from pips, tracks order lifecycle (open → closed by SL/TP) and PnL.
- **Backtest engine & metrics** — win rate, total PnL, max drawdown, Sharpe ratio, profit factor, average trade duration.
- **CLI** — run backtests with config-file or command-line overrides.

## Requirements

- Python >= 3.9

## Installation

Clone the repository, create a virtual environment, and install the package in editable mode. A virtual environment is recommended so the `forex-signals` command and its dependencies don't conflict with other Python projects.

### macOS

```bash
cd trading

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install the package
python3 -m pip install --upgrade pip
python3 -m pip install -e .

# Optional: install test dependencies (pytest, hypothesis, pytest-cov)
python3 -m pip install -e ".[dev]"
```

> If `pip` alone reports "command not found", use `python3 -m pip ...` as shown above, or `pip3 ...`.

Run the CLI:

```bash
forex-signals backtest
```

Deactivate the virtual environment when done with `deactivate`.

### Windows

Using **PowerShell**:

```powershell
cd trading

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Upgrade pip and install the package
python -m pip install --upgrade pip
python -m pip install -e .

# Optional: install test dependencies (pytest, hypothesis, pytest-cov)
python -m pip install -e ".[dev]"
```

Using **Command Prompt (cmd.exe)** instead of PowerShell, activate with:

```cmd
.venv\Scripts\activate.bat
```

> If PowerShell blocks the activation script, run this once in an elevated PowerShell session: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Run the CLI:

```powershell
forex-signals backtest
```

Deactivate the virtual environment when done with `deactivate`.

### Without a virtual environment

You can skip the venv steps and install directly, but this may conflict with other packages on your system:

```bash
pip install -e .          # macOS/Linux
python -m pip install -e . # Windows
```

This registers the `forex-signals` console command (defined in [pyproject.toml](pyproject.toml)). If the `forex-signals` command isn't found after installation, invoke the CLI via the module instead: `python -m forex_signals.cli backtest` (or `python3` on macOS).

## Configuration

Settings are read from a YAML file (default: [config.yaml](config.yaml) in the current working directory):

```yaml
pair: "EURUSD=X"
timeframe: "M5"
sl_pips: 20
tp_pips: 40
consensus_threshold: 4

strategies:
  smi:
    period: 14
    smooth_period: 3
  moving_average:
    fast_period: 10
    slow_period: 50
  rsi:
    period: 14
    overbought: 70
    oversold: 30
  macd:
    fast_period: 12
    slow_period: 26
    signal_period: 9
  bollinger:
    period: 20
    std_dev: 2.0

backtest:
  start_date: "2024-01-01"
  end_date: "2024-12-31"

# Optional: persist downloaded candles to CSV for reuse/offline analysis.
csv_export:
  enabled: false
  output_dir: "data"

# Optional: automatically search for better consensus and strategy parameters.
auto_tune:
  enabled: false
  train_split: 0.7
  consensus_threshold_values: [2, 3, 4, 5]
  strategy_param_values:
    smi:
      period: [7, 14]
      smooth_period: [2, 3]
    moving_average:
      fast_period: [5, 10]
      slow_period: [20, 50]
    rsi:
      period: [7, 14]
      overbought: [60, 70]
      oversold: [20, 30]
    macd:
      fast_period: [8, 12]
      slow_period: [20, 26]
      signal_period: [7, 9]
    bollinger:
      period: [10, 20]
      std_dev: [1.5, 2.0]
```

| Field | Description |
|---|---|
| `pair` | Yahoo Finance ticker symbol (e.g. `EURUSD=X`) |
| `timeframe` | One of `M5`, `M15`, `H1`, `H4`, `D1` |
| `sl_pips` / `tp_pips` | Stop-loss / take-profit distance in pips (must be positive) |
| `consensus_threshold` | Minimum number of agreeing strategies (1–5) needed to trigger a trade |
| `strategies` | Per-strategy parameter overrides |
| `backtest.start_date` / `end_date` | Date range for the backtest, format `YYYY-MM-DD` |
| `csv_export.enabled` | If `true`, downloaded candles are also written to a CSV file (default `false`) |
| `csv_export.output_dir` | Directory the CSV file is written into (default `data`) |
| `auto_tune.enabled` | If `true`, the backtest will automatically search for better `consensus_threshold` and strategy parameters before the final run |
| `auto_tune.train_split` | Fraction of the data used for tuning (default `0.7`) |
| `auto_tune.consensus_threshold_values` | Candidate values to try for the consensus threshold |
| `auto_tune.strategy_param_values` | Candidate values to try for each strategy parameter across all strategies |

Configuration is validated on load; invalid values raise a `ConfigError` with a descriptive message (see [src/forex_signals/config.py](src/forex_signals/config.py)).

## Usage

Run a backtest using the default `config.yaml`:

```bash
forex-signals backtest
```

Or invoke it as a module without installing the console script:

```bash
python -m forex_signals.cli backtest
```

### CLI options

All options override the corresponding value in the config file:

```bash
forex-signals backtest \
  --config config.yaml \
  --pair EURUSD=X \
  --timeframe M5 \
  --sl-pips 20 \
  --tp-pips 40 \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

| Option | Description |
|---|---|
| `--config` | Path to an alternate YAML config file |
| `--pair` | Forex pair / Yahoo Finance ticker |
| `--timeframe` | Candle timeframe (`M5`, `M15`, `H1`, `H4`, `D1`) |
| `--sl-pips` | Stop-loss in pips |
| `--tp-pips` | Take-profit in pips |
| `--start-date` | Backtest start date (`YYYY-MM-DD`) |
| `--end-date` | Backtest end date (`YYYY-MM-DD`) |
| `--save-csv` / `--no-save-csv` | Enable/disable exporting downloaded candles to a CSV file |
| `--csv-dir` | Directory to write the CSV export into (implies `--save-csv` unless `--no-save-csv` is also given) |

Example with CSV export enabled:

```bash
forex-signals backtest --save-csv --csv-dir data
```

The CSV filename is derived from the pair, timeframe, and date range, e.g. `data/EURUSDX_M5_20260601_20260729.csv`. CSV export failures (e.g. permission errors) are logged as warnings and never abort the backtest.

### Auto-tuning backtests

Enable the optional auto-tuning workflow with the CLI flag:

```bash
forex-signals backtest --auto-tune
```

You can also enable it through the config file by setting:

```yaml
auto_tune:
  enabled: true
```

When auto-tuning is enabled, the system evaluates candidate configurations on an initial training slice of the data, then uses the best-performing combination for the full backtest run.

The tuning run also writes a CSV log file such as `data/auto_tune_results_EURUSDX.csv` so you can inspect the search process afterward. Each row represents one tested configuration. The main columns are:

- `score` — the ranking value used to compare candidates; higher is better.
- `max_drawdown` — the largest peak-to-trough decline seen in that candidate's training backtest; lower is better.
- `win_rate` — the fraction of closed trades that ended profitably; higher is better.
- `consensus_threshold` — the minimum agreement level used for that candidate.
- `strategy.parameter` columns — the parameter values used for each strategy, such as `smi.period`, `macd.fast_period`, or `bollinger.std_dev`.

In practice, a good candidate usually has a high `score`, a low `max_drawdown`, and a high `win_rate`.

### Example output

```
Downloading EURUSD=X data (M5) from 2024-01-01 to 2024-12-31...
Downloaded 12345 candles.

==================================================
         BACKTEST RESULTS
==================================================

  Total Trades         │  42
  Win Rate              │  57.14%
  Total PnL             │  0.012340
  Max Drawdown          │  0.003210
  Sharpe Ratio          │  1.2345
  Profit Factor         │  1.8000
  Avg Trade Duration    │  3600s

==================================================
```

## Live Trading with MetaTrader 5 on macOS (Method A)

The system supports live and demo automated execution on macOS using a **Local TCP Socket Bridge (Method A)**:

```
┌─────────────────────────┐   Local TCP Socket   ┌────────────────────────────────┐
│   macOS Python App      │ ◄──────────────────► │  MT5 for Mac (Wine Container)  │
│  (forex-signals live)   │  (127.0.0.1:5555)    │  - ForexBridge.mq5 on Chart    │
└─────────────────────────┘      JSON Messages   └────────────────────────────────┘
```

### Setup Steps:

1. **Install MT5 for Mac**: Download and install MetaTrader 5 from your broker or [MetaQuotes](https://www.metatrader5.com/en/download).
2. **Install the Bridge EA**:
   - Open MT5 on Mac -> **File** -> **Open Data Folder**.
   - Navigate to `MQL5/Experts/` and copy `scripts/mt5/ForexBridge.mq5` into it.
   - Open MT5 Navigator (`Cmd+N` or `Ctrl+N`), right-click **Expert Advisors** -> **Refresh**.
   - Drag `ForexBridge` onto any active chart (e.g. `EURUSD`).
   - Enable **Allow Algo Trading** in the MT5 toolbar and in the EA properties dialog.
3. **Run Live Trading**:
   ```bash
   # Live execution connecting to local MT5 on Mac:
   forex-signals live --config config.yaml

   # Or run with mock broker for offline testing:
   forex-signals live --mock
   ```

## Project Structure

```
config.yaml                  # Default configuration & MT5 bridge settings
pyproject.toml                # Package metadata, dependencies, console script
scripts/
  mt5/
    ForexBridge.mq5           # MQL5 Expert Advisor bridge for MT5 on macOS (Method A)
src/forex_signals/
  cli.py                      # CLI entry point (backtest, live)
  config.py                   # Config loading & validation
  data/
    downloader.py              # Yahoo Finance downloader
    models.py                   # Core enums & dataclasses (Candle, Signal, Order, ...)
  strategies/                  # SMI, Moving Average, RSI, MACD, Bollinger Bands
  consensus/
    engine.py                   # Consensus voting logic
  orders/
    manager.py                  # Order creation & lifecycle management
  backtest/
    engine.py                   # Backtest orchestrator
    metrics.py                   # Win rate, PnL, drawdown, Sharpe, profit factor
    tuner.py                   # Grid search auto-tuner & CSV persistence
  broker/
    base.py                    # Broker protocol
    models.py                  # Account, symbol, position, execution models
    socket_client.py           # TCP socket client for macOS MT5 (Method A)
    live_runner.py             # Live trading synchronization loop
    mock.py                    # Mock broker for offline testing & CI
tests/                         # Unit and property tests mirroring package structure
```

## Extending

- **Add a new strategy**: implement the `Strategy` protocol in [src/forex_signals/strategies/base.py](src/forex_signals/strategies/base.py) (`name`, `generate_signal(candles)`, `min_candles`), then register it in `_build_strategies` in [src/forex_signals/cli.py](src/forex_signals/cli.py) and add its parameters to `config.yaml`.
- **Live trading**: the `broker` package provides both live MetaTrader 5 socket execution (`SocketBrokerClient`) and simulated execution (`MockBrokerClient`).

## Testing

Run the full test suite with:

```bash
pytest
```

Tests are organized under [tests/](tests) mirroring the package layout (`test_strategies/`, `test_consensus/`, `test_orders/`, `test_backtest/`, `test_data/`, `test_config/`, `test_cli/`, `test_broker/`).

## Notes / Current Scope

- Single pair, single timeframe per run (multi-pair support is a future extension).
- Stop-loss/take-profit are fixed-pip only (ATR-based sizing is a future extension).
- All 5 strategies are equally weighted in consensus (weighted consensus is a future extension).
- MetaTrader 5 live/demo trading integration on macOS uses the **Local TCP Socket Bridge (Method A)**, as specified in [requirements.md](requirements.md), detailed in [.kiro/specs/forex-trading-signal-system/design.md](.kiro/specs/forex-trading-signal-system/design.md), and tracked in [.kiro/specs/forex-trading-signal-system/tasks.md](.kiro/specs/forex-trading-signal-system/tasks.md).
