# Requirements Specification: Forex Trading Signal System

## Overview

A Python application that downloads forex data, applies 5 technical analysis strategies, and generates buy/sell signals when 4 out of 5 strategies agree on direction. Orders include configurable stop-loss and take-profit levels. The system runs locally in backtesting mode with comprehensive performance metrics.

## Functional Requirements

### FR1: Data Download

- Download forex candlestick data from Yahoo Finance
- Default timeframe: 5-minute candles (M5)
- Configurable timeframe (M5, M15, H1, H4, D1, etc.)
- Single pair initially (e.g., EUR/USD), designed for multi-pair extension later

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
