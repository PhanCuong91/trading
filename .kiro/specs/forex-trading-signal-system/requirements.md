# Requirements Specification: Forex Trading Signal System

## Overview

The Forex Trading Signal System is a modular Python application designed for algorithmic forex trading. It provides end-to-end functionality for both historical backtesting and live/demo trading execution through MetaTrader 5 (MT5).

The system downloads market data, evaluates 5 independent technical analysis strategies, and generates trade signals when a configurable consensus (default: 4 out of 5 strategies) agree on market direction. Orders include configurable stop-loss and take-profit levels.

For live trading, the system directly interfaces with MetaTrader 5 via the official `MetaTrader5` Python module (`mt5.initialize()`, `mt5.order_send()`, `mt5.copy_rates_from_pos()`), configured to run on Ubuntu on Raspberry Pi 5 (ARM64 via Box64/Wine64 headless environment), Windows, and Linux. The system also supports local backtesting with automated parameter tuning, comprehensive performance analytics, and a built-in mock broker for offline testing.

---

## Functional Requirements

### FR1: Market Data Ingestion & Storage

- **FR1.1 Yahoo Finance Historical Data**: Download historical forex candlestick data via Yahoo Finance for backtesting and strategy evaluation.
- **FR1.2 Configurable Timeframes**: Support standard timeframe intervals, including M1, M5 (default), M15, M30, H1, H4, D1.
- **FR1.3 Currency Pair Configuration**: Support configurable currency pairs (e.g., `EURUSD=X`, `GBPUSD=X`, `USDJPY=X`), with extensible design for multi-pair support.
- **FR1.4 Data Persistence (CSV Export)**:
  - Persist downloaded candlestick data to local CSV files (`data/<pair>_<timeframe>_<start>_<end>.csv`).
  - Sanitize pair symbols for filesystem-safe file naming.
  - CSV export is optional/configurable and does not block the backtesting or trading pipeline if disabled or if writing fails.
- **FR1.5 Data Quality & Gap Handling**:
  - Validate candle OHLC integrity (High >= Low, High >= Open, High >= Close, Volume >= 0).
  - Implement retry mechanism with exponential backoff (default: 3 attempts) for data download.
  - Detect and log data gaps or missing periods.

### FR2: Technical Analysis Trading Strategies

The system includes 5 standalone technical indicator strategies conforming to a unified strategy interface (`generate_signal(candles) -> Signal.BUY | Signal.SELL | Signal.NEUTRAL`):

- **FR2.1 SMI (Stochastic Momentum Index)**:
  - Calculate price distance relative to the midpoint of the high/low range over a configurable period (default: 14).
  - Apply double exponential smoothing (`smooth_period` default: 3).
  - Generate BUY when SMI crosses above oversold threshold (default: -40).
  - Generate SELL when SMI crosses below overbought threshold (default: +40).
- **FR2.2 Moving Average Crossover**:
  - Calculate fast moving average (default period: 10) and slow moving average (default period: 50).
  - Support SMA and EMA calculations.
  - Generate BUY on golden cross (fast crosses above slow).
  - Generate SELL on death cross (fast crosses below slow).
- **FR2.3 RSI (Relative Strength Index)**:
  - Standard 14-period RSI with Wilder smoothing.
  - Generate BUY when RSI crosses above oversold threshold (default: 30).
  - Generate SELL when RSI crosses below overbought threshold (default: 70).
- **FR2.4 MACD (Moving Average Convergence Divergence)**:
  - Standard MACD configuration (fast: 12, slow: 26, signal: 9).
  - Calculate MACD line, Signal line, and MACD Histogram.
  - Generate BUY on MACD line crossing above Signal line.
  - Generate SELL on MACD line crossing below Signal line.
- **FR2.5 Bollinger Bands**:
  - Standard 20-period SMA with configurable standard deviation multiplier (default: 2.0).
  - Generate BUY when price touches/crosses below lower band and reverses upward.
  - Generate SELL when price touches/crosses above upper band and reverses downward.
- **FR2.6 Insufficient Data Handling**: Return `Signal.NEUTRAL` without error whenever the input candle sequence is shorter than the strategy's minimum required candle count (`min_candles`).

### FR3: Consensus Engine

- **FR3.1 Strategy Weighting**: Apply equal weighting across all 5 configured strategies.
- **FR3.2 Consensus Threshold**:
  - Configurable agreement threshold (default: 4 out of 5 strategies).
  - Trigger BUY signal when >= threshold strategies vote BUY.
  - Trigger SELL signal when >= threshold strategies vote SELL.
- **FR3.3 Neutral Resolution**: Output `Signal.NEUTRAL` (no trade) when fewer than threshold strategies agree or when conflicting consensus occurs.

### FR4: Order Management & Lifecycle

- **FR4.1 Order Creation**:
  - Create BUY or SELL orders automatically upon consensus trigger.
  - Record order timestamp, pair, direction, entry price, lot size, stop-loss price, and take-profit price.
- **FR4.2 Stop-Loss & Take-Profit Calculation**:
  - Calculate fixed pip stop-loss (default: 20 pips, configurable).
  - Calculate fixed pip take-profit (default: 40 pips, configurable).
  - Accurate pip-to-price conversion based on currency pair pip size (e.g., 0.0001 for EUR/USD, 0.01 for USD/JPY).
- **FR4.3 Order Lifecycle Management**:
  - Track order states: `PENDING`, `OPEN`, `CLOSED_BY_SL`, `CLOSED_BY_TP`, `CLOSED_BY_SIGNAL`, `CANCELLED`.
  - Maintain comprehensive order execution logs including exit price, exit timestamp, profit/loss (pips and currency), and exit reason.
- **FR4.4 Risk & Position Constraints**:
  - Configurable maximum open positions per symbol (default: 1).
  - Prevent conflicting opposite positions or duplicate entries.

### FR5: Backtesting Engine & Performance Analytics

- **FR5.1 Bar-by-Bar Simulation**:
  - Simulate historical trade execution bar-by-bar using historical OHLC data.
  - Evaluate intrabar SL/TP hits using High/Low candle extremes.
  - Account for configurable spread and slippage.
- **FR5.2 Performance Metrics**:
  - Total and Net P&L (in pips and account currency).
  - Win rate (percentage of profitable trades).
  - Total number of trades (winning, losing, break-even).
  - Maximum Drawdown (monetary amount and peak-to-trough percentage).
  - Sharpe Ratio (annualized risk-adjusted return).
  - Sortino Ratio (downside risk-adjusted return).
  - Profit Factor (Gross Profit / Gross Loss).
  - Average Trade Duration and Average Win / Loss ratio.
- **FR5.3 Reporting**:
  - Display formatted CLI summary tables.
  - Export backtest results to JSON or CSV logs.

### FR6: Automated Parameter Auto-Tuning

- **FR6.1 Grid Search & Parameter Exploration**:
  - Search over candidate combinations of `consensus_threshold` (e.g. 2, 3, 4, 5) and all parameters across all 5 strategies.
  - User-configurable parameter search ranges in configuration file.
- **FR6.2 Training/Validation Data Split**:
  - Support splitting historical data (e.g., 70% training, 30% out-of-sample validation).
- **FR6.3 Performance Evaluation & Objective Scoring**:
  - Score candidates using configurable target metrics (primary: Sharpe Ratio, fallback: Profit Factor).
- **FR6.4 Incremental CSV Persistence & Resumption**:
  - Persist every evaluated candidate to a CSV log with `score`, `max_drawdown`, `win_rate`, `consensus_threshold`, and all strategy parameter values.
  - On restart, read the existing tuning CSV file and automatically skip previously evaluated parameter combinations.
- **FR6.5 Real-Time Progress Feedback**:
  - Emit frequent, visible progress updates (start, current candidate index, progress percentage, current best score).
- **FR6.6 Final Execution**:
  - Automatically select the best-performing configuration and execute the final backtest with winning parameters.

### FR7: MetaTrader 5 (MT5) Live Trading via Direct Python Module (`MetaTrader5`)

- **FR7.1 Direct Python Module Connection & Lifecycle**:
  - Direct integration and communication using the official `MetaTrader5` Python module (`import MetaTrader5 as mt5`).
  - Support configurable terminal connection parameters: terminal executable `path`, account `login`, `password`, `server`, and initialization `timeout` via `mt5.initialize()`.
  - Handle clean shutdown via `mt5.shutdown()` on application exit or SIGINT/SIGTERM signals.
  - Connection health checks via `mt5.terminal_info()` with automatic reconnection logic if the connection is interrupted.
- **FR7.2 Symbol & Account Synchronization**:
  - Query real-time account status using `mt5.account_info()`: balance, equity, margin, free margin, currency, and leverage.
  - Query symbol specification via `mt5.symbol_info()` and `mt5.symbol_info_tick()`: broker symbol name (e.g., `EURUSD`, `EURUSDm`), digits, point value, spread in pips/points, minimum/maximum lot size, lot step, and minimum stop level distance (`stoplevel` / `trade_stops_level`).
  - Automatically verify and activate symbol in Market Watch via `mt5.symbol_select(symbol, True)`.
- **FR7.3 Live Market Data Retrieval**:
  - Fetch historical and live candlestick data directly using `mt5.copy_rates_from_pos()` or `mt5.copy_rates_range()`.
  - Transform MT5 rate structures (time, open, high, low, close, tick_volume, spread) into standardized application `Candle` data models.
  - Synchronize data polling to timeframe bar completion intervals.
- **FR7.4 Direct Live Order Execution & SL/TP Enforcement**:
  - Dispatch market orders using `mt5.order_send()` with structured `MqlTradeRequest` (`TRADE_ACTION_DEAL`, `ORDER_TYPE_BUY` / `ORDER_TYPE_SELL`, volume, price, stoploss, takeprofit, deviation, magic number, comment).
  - Enforce SL/TP distance compliance strictly respecting broker digits and minimum stop level (`stoplevel`).
  - Apply slippage deviation in points (`deviation`).
  - Tag orders with unique `magic_number` (e.g., `100101`) and custom comment for complete bot isolation.
  - Verify trade return codes (`retcode == 10009` for `TRADE_RETCODE_DONE`) and log execution results.
- **FR7.5 Live Position Tracking & Management**:
  - Query open positions using `mt5.positions_get(symbol=..., magic=...)`.
  - Send position close requests via `mt5.order_send()` with opposite action (`TRADE_ACTION_DEAL`, closing order type) upon opposite consensus signals, SL/TP execution, or manual stop.
  - Real-time tracking and logging of trade tickets, P&L, and detailed broker return codes / error logs (`mt5.last_error()`).
- **FR7.6 Risk Safeguards & Safety Controls**:
  - Spread filter: compare current live spread against `max_spread_pips` and reject order dispatch if spread is excessive.
  - Margin & balance verification prior to order placement.
  - Built-in Mock Broker Client conforming to the same interface for offline development, unit tests, and CI without requiring an active MT5 terminal or Wine setup.
- **FR7.7 Ubuntu Raspberry Pi 5 Deployment & Headless Execution**:
  - Support execution on Ubuntu on Raspberry Pi 5 (ARM64) running the MT5 terminal and Python environment via Box64 + Wine64 or containerized headless virtual desktop (Xvfb).
  - Low CPU and memory footprint optimized for continuous 24/7 execution on Raspberry Pi 5 (4GB / 8GB RAM).
  - Support execution as a background system service (e.g. systemd service) with structured logging.

### FR8: Automated Testing & Validation

- **FR8.1 Strategy Unit Tests**: Unit tests for all 5 strategies covering standard patterns, boundary conditions, flat prices, and insufficient candle buffers.
- **FR8.2 Consensus Engine Integration Tests**: Verify consensus thresholds, tie conditions, and neutral signals.
- **FR8.3 Backtest Result Validation**: Regression tests verifying metric calculation accuracy (Sharpe, Drawdown, Win Rate, Profit Factor).
- **FR8.4 Broker Client & Mock Bridge Tests**: Unit and integration tests with mocked `MetaTrader5` module functions and Mock Broker verifying connection lifecycle, account queries, order placement, return codes, error handling, and position tracking.

---

## Non-Functional Requirements

- **NFR1: Modular Architecture**: Strict separation of concerns across Data, Strategies, Consensus, Orders, Backtest, Broker/MT5, and CLI packages.
- **NFR2: Ubuntu Raspberry Pi 5 & Direct Python MT5 Integration**: Direct integration using the `MetaTrader5` Python module with support for execution on Ubuntu on Raspberry Pi 5 (via Wine64/Box64 headless setup), Linux x86_64, and Windows.
- **NFR3: Configuration Flexibility**: Full configuration via `config.yaml` with CLI flag overrides (`--path`, `--login`, `--server`, `--mock`, etc.).
- **NFR4: Reliability & Network Resilience**: Reconnection backoff, error handling, no silent crashes, and clear diagnostic error logs.
- **NFR5: Cross-Platform Support**: Core backtest engine, strategy pipeline, and broker interface run consistently across Ubuntu Linux (Raspberry Pi 5 ARM64 & x86_64), macOS (backtest/mock), and Windows.
- **NFR6: Low Latency Execution**: Direct Python IPC communication under 5ms; bar processing and order dispatch under 15ms.

---

## Out of Scope (Future Phases)

- ATR-based dynamic stop-loss/take-profit calculations
- Multi-pair portfolio trading running simultaneously across correlated pairs
- Machine learning / dynamic weight allocation for consensus voting
- Web-based graphical dashboard and cloud multi-tenant deployment
