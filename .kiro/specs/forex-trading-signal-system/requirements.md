# Requirements Specification: Forex Trading Signal System

## Overview

A Python application that downloads forex data, applies 5 technical analysis strategies, and generates buy/sell signals when 4 out of 5 strategies agree on direction. Orders include configurable stop-loss and take-profit levels. The system runs locally in backtesting mode with comprehensive performance metrics.

## Functional Requirements

### FR1: Data Download

- Download forex candlestick data from Yahoo Finance
- Default timeframe: 5-minute candles (M5)
- Configurable timeframe (M5, M15, H1, H4, D1, etc.)
- Single pair initially (e.g., EUR/USD), designed for multi-pair extension later
- Persist downloaded candlestick data to a local CSV file (e.g. `data/<pair>_<timeframe>_<start>_<end>.csv`)
- CSV export is optional/configurable and does not block the backtest pipeline if disabled

### FR2: Trading Strategies

Five strategies, each producing a BUY, SELL, or NEUTRAL signal:

1. SMI (Stochastic Momentum Index)
2. Moving Average (e.g., crossover of fast/slow MA)
3. RSI (Relative Strength Index)
4. MACD (Moving Average Convergence Divergence)
5. Bollinger Bands

### FR3: Consensus Engine

- Equal weight for all 5 strategies
- Signal generated when 4 out of 5 strategies agree on direction
- If fewer than 4 agree → no trade (NEUTRAL)

### FR4: Order Management

- Generate BUY or SELL orders based on consensus
- Stop-loss: fixed pips (configurable), extensible to ATR-based later
- Take-profit: fixed pips (configurable)
- Track order lifecycle (open, closed by SL, closed by TP)

### FR5: Backtesting & Performance Metrics

- Run strategies against historical Yahoo Finance data
- Metrics:
  - Win rate
  - Total P&L
  - Max drawdown
  - Sharpe ratio
  - Profit factor
  - Average trade duration
  - Number of trades

### FR6: Automated Testing

- Unit tests for each strategy
- Integration tests for the consensus engine
- Backtest result validation tests

### FR7: Auto-Tuning for Backtesting

- Support an optional auto-tuning mode for backtesting
- In this mode, the system shall search over candidate values for `consensus_threshold` and all strategy parameters across all configured strategies
- The system shall evaluate each candidate configuration using a defined performance metric (e.g., Sharpe ratio or profit factor)
- The system shall persist each evaluated candidate result to a CSV file, including the selected metric value, `consensus_threshold`, and the parameters used for every strategy
- Each persisted tuning record shall also include the resulting backtest metrics needed for comparison, including `score`, `max_drawdown`, and `win_rate`
- The system shall provide frequent, visible progress/status feedback during long-running auto-tuning sessions so users can clearly see that tuning is actively running, including messages at the start of tuning, before each candidate evaluation, and when a candidate completes or becomes the current best result
- When auto-tuning resumes, the system shall check the existing tuning CSV file first and skip re-running any candidate combination that is already recorded there
- The best-performing configuration shall be selected and used for the final backtest run
- Auto-tuning shall remain optional and shall not change the current behavior when disabled

## Non-Functional Requirements

- Modular package structure with clear separation of concerns
- Extensibility: easy to add new strategies, new pairs, ATR-based SL/TP
- MetaTrader 5 integration: planned for future phase (not in initial scope, but architecture should accommodate it)
- Configurable: pair, timeframe, SL/TP pips, strategy parameters via config file or CLI

## Out of Scope (Future Phases)

- MetaTrader 5 live trading integration
- ATR-based dynamic stop-loss/take-profit
- Multiple forex pairs simultaneously
- Weighted strategy consensus
