# Requirements Specification: Forex Trading Signal System

## Overview

The Forex Trading Signal System is a modular Python application designed for algorithmic forex trading. It provides end-to-end functionality for both historical backtesting and live/demo trading execution through MetaTrader 5 (MT5).

The system downloads market data, evaluates 5 independent technical analysis strategies, and generates trade signals when a configurable consensus (default: 4 out of 5 strategies) agree on market direction. Orders include configurable stop-loss and take-profit levels.

For live trading on macOS, the system employs a **Local TCP Socket Bridge (Method A)** connecting native macOS Python to MetaTrader 5 running on Mac via a lightweight MQL5 Expert Advisor (`ForexBridge.mq5`). The system also supports local backtesting with automated parameter tuning, comprehensive performance analytics, and a built-in mock broker for offline testing.

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

### FR7: MetaTrader 5 (MT5) Live Trading via Local TCP Socket Bridge (macOS Native)

- **FR7.1 Local TCP Socket Bridge Architecture (Method A)**:
  - Provide an MQL5 Expert Advisor script (`ForexBridge.mq5`) running inside MT5 on macOS (or Windows) that starts a local TCP server on `127.0.0.1:<port>` (default: `5555`).
  - Native macOS Python client connects via standard TCP sockets and exchanges structured JSON requests and responses.
  - Heartbeat / ping mechanism with automatic reconnection and exponential backoff if the socket connection drops.
- **FR7.2 Symbol & Account Synchronization via Socket**:
  - Query real-time account info (`ACCOUNT_INFO`): balance, equity, margin, free margin, currency, leverage.
  - Query symbol specification (`SYMBOL_INFO`): broker symbol name (e.g., `EURUSD`, `EURUSDm`), digits, point value, spread in pips, minimum/maximum lot size, lot step, and minimum stop level (`stoplevel`).
- **FR7.3 Live Market Data Streaming**:
  - Query historical and live candles (`GET_CANDLES`) directly from the MT5 chart buffer.
  - Maintain synchronized in-memory candle series aligned with candle completion intervals.
- **FR7.4 Live Order Execution & SL/TP Enforcement**:
  - Send market order requests (`ORDER_SEND`) with action (`BUY` / `SELL`), volume, symbol, calculated stop-loss, and take-profit.
  - Ensure SL and TP prices strictly respect broker digits and minimum stop level distance (`stoplevel`).
  - Apply slippage deviation in points.
  - Tag orders with unique `magic_number` (e.g., `100101`) and custom comment for complete bot isolation.
- **FR7.5 Live Position Tracking & Management**:
  - Query open positions (`GET_POSITIONS`) filtered by bot `magic_number`.
  - Send position close requests (`ORDER_CLOSE`) upon opposite consensus signals, SL/TP execution, or manual stop.
  - Real-time logging of execution status and broker return codes (e.g. `10009` for `TRADE_RETCODE_DONE`).
- **FR7.6 Risk Safeguards & Safety Controls**:
  - Spread filter: reject order dispatch if live spread exceeds `max_spread_pips`.
  - Margin & balance verification before order placement.
  - Built-in Mock Broker Client for offline development, tests, and CI without requiring an active MT5 terminal.

### FR8: Automated Testing & Validation

- **FR8.1 Strategy Unit Tests**: Unit tests for all 5 strategies covering standard patterns, boundary conditions, flat prices, and insufficient candle buffers.
- **FR8.2 Consensus Engine Integration Tests**: Verify consensus thresholds, tie conditions, and neutral signals.
- **FR8.3 Backtest Result Validation**: Regression tests verifying metric calculation accuracy (Sharpe, Drawdown, Win Rate, Profit Factor).
- **FR8.4 Broker Socket & Mock Bridge Tests**: Unit and integration tests with mocked TCP socket and Mock Broker verifying connection lifecycle, message framing, order placement, error codes, and position tracking.

---

## Non-Functional Requirements

- **NFR1: Modular Architecture**: Strict separation of concerns across Data, Strategies, Consensus, Orders, Backtest, Broker/MT5, and CLI packages.
- **NFR2: Native macOS Compatibility (Method A)**: Seamless execution from macOS terminal with native Python (3.10+) communicating over local TCP socket to MT5 for Mac without requiring Wine commands or Windows virtualization.
- **NFR3: Configuration Flexibility**: Full configuration via `config.yaml` with CLI flag overrides (`--host`, `--port`, `--mock`, etc.).
- **NFR4: Reliability & Network Resilience**: Reconnection backoff, socket timeout handling, no silent crashes, and clear diagnostic error logs.
- **NFR5: Cross-Platform Support**: Core backtest engine and socket broker client run identically across macOS, Linux, and Windows.
- **NFR6: Low Latency Execution**: Socket round-trip communication under 5ms on localhost; bar processing and order dispatch under 15ms.

---

## Out of Scope (Future Phases)

- ATR-based dynamic stop-loss/take-profit calculations
- Multi-pair portfolio trading running simultaneously across correlated pairs
- Machine learning / dynamic weight allocation for consensus voting
- Web-based graphical dashboard and cloud multi-tenant deployment
