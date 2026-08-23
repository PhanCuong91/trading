# Implementation Plan: Forex Trading Signal System

## Overview

Build a Python forex trading signal system supporting both historical backtesting (with automated strategy auto-tuning) and live/demo trading integration via MetaTrader 5 on macOS using **Method A: Local TCP Socket Bridge**.

The pipeline architecture is: Market Data (Yahoo/MT5 Socket) → Strategy Engine (5 strategies) → Consensus Engine (4/5 voting) → Order Manager / Risk Engine → Backtest Engine / Socket MT5 Broker Execution.

---

## Tasks

- [x] 1. Set up project structure, data models, and configuration
  - [x] 1.1 Create project skeleton with pyproject.toml and package structure
    - Create `pyproject.toml` with dependencies (yfinance, pandas, numpy, pyyaml, click)
    - Create `src/forex_signals/__init__.py` and all subpackage `__init__.py` files
    - Create directory structure: `data/`, `strategies/`, `consensus/`, `orders/`, `backtest/`, `broker/`
    - Create `tests/conftest.py` and test subdirectories
    - Create default `config.yaml` with all strategy parameters
    - _Requirements: NFR1, NFR3_

  - [x] 1.2 Implement data models and enums
    - Create `src/forex_signals/data/models.py` with `Timeframe`, `Signal`, `OrderStatus` enums
    - Create `Candle`, `StrategySignal` frozen dataclasses
    - Create `Order` dataclass with lifecycle fields
    - Create `BacktestConfig` and `BacktestResult` dataclasses
    - _Requirements: FR1, FR4, FR5_

  - [x] 1.3 Implement configuration loading and validation
    - Create `src/forex_signals/config.py` with YAML loading
    - Validate all configuration values (positive pips, valid timeframe, valid dates)
    - Raise `ConfigError` with descriptive messages on invalid config
    - Support CLI overrides for pair, timeframe, SL/TP pips
    - _Requirements: NFR3, FR1.2, FR1.3_

  - [x] 1.4 Implement Yahoo Finance data downloader
    - Create `src/forex_signals/data/downloader.py` with `YahooDataDownloader` class
    - Download OHLC data using yfinance, convert to `List[Candle]`
    - Implement retry with exponential backoff (3 attempts)
    - Raise `DataDownloadError` on failure
    - Detect and log data gaps
    - _Requirements: FR1.1, FR1.5_

  - [x] 1.5 Implement CSV export for downloaded candle data
    - Add `export_to_csv` method to `YahooDataDownloader` writing candles to CSV with columns `timestamp, open, high, low, close, volume`
    - Derive filename from pair, timeframe, and date range (`data/<pair>_<timeframe>_<start>_<end>.csv`)
    - Create the output directory if it does not exist
    - CSV write failures are logged as warnings and do not abort the backtest
    - _Requirements: FR1.4_

- [x] 2. Implement technical trading strategies
  - [x] 2.1 Implement strategy base protocol
    - Create `src/forex_signals/strategies/base.py` with `Strategy` Protocol
    - Define `name`, `generate_signal(candles)`, and `min_candles` interface
    - _Requirements: FR2, NFR1_

  - [x] 2.2 Implement SMI strategy
    - Create `src/forex_signals/strategies/smi.py`
    - Calculate distance from close to midpoint of high-low range
    - Double EMA smoothing with configurable period and smooth_period
    - BUY on SMI crossing above -40, SELL on crossing below +40
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.1, FR2.6_

  - [x] 2.3 Implement Moving Average crossover strategy
    - Create `src/forex_signals/strategies/moving_average.py`
    - Configurable fast_period (default 10) and slow_period (default 50)
    - BUY on golden cross, SELL on death cross, NEUTRAL otherwise
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.2, FR2.6_

  - [x] 2.4 Implement RSI strategy
    - Create `src/forex_signals/strategies/rsi.py`
    - Standard 14-period RSI calculation
    - BUY when RSI crosses above oversold (30), SELL when crosses below overbought (70)
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.3, FR2.6_

  - [x] 2.5 Implement MACD strategy
    - Create `src/forex_signals/strategies/macd.py`
    - Standard MACD (12, 26, 9) calculation
    - BUY on MACD crossing above signal, SELL on crossing below
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.4, FR2.6_

  - [x] 2.6 Implement Bollinger Bands strategy
    - Create `src/forex_signals/strategies/bollinger.py`
    - 20-period SMA with configurable std_dev bands
    - BUY on price touching/crossing below lower band and reversing
    - SELL on price touching/crossing above upper band and reversing
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.5, FR2.6_

  - [ ]* 2.7 Write property tests for strategy signal validity
    - **Property 1: Strategy signal validity**
    - For any valid candle sequence with sufficient length and for any strategy, `generate_signal` returns exactly BUY, SELL, or NEUTRAL without raising
    - **Validates: Requirements FR2.1, FR2.2, FR2.3, FR2.4, FR2.5, FR2.6**

  - [x] 2.8 Write unit tests for all strategies
    - Test each strategy with known price patterns that produce expected signals
    - Test NEUTRAL output when insufficient candles provided
    - Test edge cases (flat prices, extreme values)
    - _Requirements: FR2, FR8.1_

- [x] 3. Implement consensus engine
  - [x] 3.1 Implement consensus engine logic
    - Create `src/forex_signals/consensus/engine.py` with `ConsensusEngine` class
    - Configurable threshold (default 4)
    - Count BUY and SELL signals; return direction if count >= threshold, else NEUTRAL
    - _Requirements: FR3.1, FR3.2, FR3.3_

  - [ ]* 3.2 Write property tests for consensus threshold correctness
    - **Property 2: Consensus threshold correctness**
    - For any list of 5 signals, consensus returns BUY iff >=4 are BUY, SELL iff >=4 are SELL, NEUTRAL otherwise
    - **Validates: Requirements FR3.2, FR3.3**

  - [ ]* 3.3 Write property tests for consensus symmetry
    - **Property 3: Consensus symmetry (equal weight)**
    - For any list of 5 signals and any permutation, consensus produces the same result
    - **Validates: Requirements FR3.1**

  - [x] 3.4 Write integration tests for consensus engine
    - Test consensus with mixed signals below threshold → NEUTRAL
    - Test consensus with 4 BUY + 1 SELL → BUY
    - Test consensus with 4 SELL + 1 NEUTRAL → SELL
    - Test with all 5 agreeing → signal matches
    - _Requirements: FR3, FR8.2_

- [x] 4. Checkpoint - Ensure strategies and consensus tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement order management
  - [x] 5.1 Implement Order models and OrderManager
    - Create `src/forex_signals/orders/models.py`
    - Create `src/forex_signals/orders/manager.py` with `OrderManager` class
    - `create_order`: calculate SL/TP prices from pips and pip_value (0.0001)
    - `update_order`: check candle high/low against SL/TP levels, close if hit
    - Track PnL on close
    - _Requirements: FR4.1, FR4.2, FR4.3, FR4.4_

  - [ ]* 5.2 Write property tests for SL/TP price calculation
    - **Property 4: Stop-loss and take-profit price calculation**
    - For any entry price and positive SL/TP pips: BUY → SL < entry < TP; SELL → TP < entry < SL
    - Distance from entry equals pips * pip_value
    - **Validates: Requirements FR4.2**

  - [ ]* 5.3 Write property tests for order lifecycle state machine
    - **Property 5: Order lifecycle state machine**
    - Open order closes iff candle price range intersects SL or TP; once closed, status never changes
    - **Validates: Requirements FR4.3**

  - [x] 5.4 Write unit tests for order management
    - Test BUY order creation with correct SL/TP
    - Test SELL order creation with correct SL/TP
    - Test order closed by TP (candle high hits TP for BUY)
    - Test order closed by SL (candle low hits SL for BUY)
    - Test order remains open when candle doesn't hit SL/TP
    - _Requirements: FR4, FR8.1_

- [x] 6. Implement backtest engine and metrics
  - [x] 6.1 Implement metrics calculator
    - Create `src/forex_signals/backtest/metrics.py` with `MetricsCalculator` class
    - Implement: `win_rate`, `total_pnl`, `max_drawdown`, `sharpe_ratio`, `profit_factor`, `avg_trade_duration`
    - Handle edge cases: empty trades, zero std dev, no losing trades
    - _Requirements: FR5.2_

  - [ ]* 6.2 Write property tests for win rate metric
    - **Property 6: Win rate metric correctness**
    - For any non-empty list of closed trades, win rate = count(pnl > 0) / total, always in [0.0, 1.0]
    - **Validates: Requirements FR5.2**

  - [ ]* 6.3 Write property tests for max drawdown
    - **Property 7: Max drawdown non-negativity and correctness**
    - For any sequence of trades, max drawdown >= 0 and equals max peak-to-trough in cumulative PnL
    - **Validates: Requirements FR5.2**

  - [ ]* 6.4 Write property tests for profit factor
    - **Property 8: Profit factor correctness**
    - Profit factor = gross_profit / abs(gross_loss); inf if no losers, 0.0 if no winners
    - **Validates: Requirements FR5.2**

  - [ ]* 6.5 Write property tests for total PnL additivity
    - **Property 9: Total PnL additivity**
    - total_pnl(A + B) == total_pnl(A) + total_pnl(B) for any partition
    - **Validates: Requirements FR5.2**

  - [ ]* 6.6 Write property tests for Sharpe ratio
    - **Property 10: Sharpe ratio formula correctness**
    - For 2+ trades with non-zero std: sharpe = (mean - rfr) / std; otherwise 0.0
    - **Validates: Requirements FR5.2**

  - [x] 6.7 Implement backtest engine orchestrator
    - Create `src/forex_signals/backtest/engine.py` with `BacktestEngine` class
    - Process candles sequentially: generate signals → consensus → create order if signal and no open position → update open orders
    - After all candles, compute and return `BacktestResult`
    - _Requirements: FR5.1, FR5.2, FR5.3_

  - [x] 6.8 Write unit tests for backtest engine
    - Test with known data producing predictable trades
    - Validate metrics match manual calculations
    - Test no-trade scenario (never reaches consensus)
    - _Requirements: FR5, FR8.3_

- [x] 7. Implement auto-tuning for backtesting
  - [x] 7.1 Implement grid search tuner and CSV logging
    - Create `src/forex_signals/backtest/tuner.py` with `AutoTuningEngine`
    - Vary `consensus_threshold` and all strategy parameters across configured search space
    - Split dataset into train (e.g. 70%) and evaluation segments
    - Persist results incrementally to CSV with `score`, `max_drawdown`, `win_rate`, `consensus_threshold`, and parameter dictionary
    - Skip already-evaluated combinations when resuming
    - Emit visible status/progress messages
    - _Requirements: FR6.1, FR6.2, FR6.3, FR6.4, FR6.5, FR6.6_

  - [x] 7.2 Write unit and integration tests for auto-tuner
    - Test grid generation, train splitting, CSV incremental persistence, resume skip logic, and best candidate selection
    - _Requirements: FR6, FR8.3_

- [x] 8. Implement MetaTrader 5 live trading via Local TCP Socket Bridge (Method A)
  - [x] 8.1 Define Broker protocol and MT5 data models
    - Create `src/forex_signals/broker/base.py` defining `Broker` Protocol (`connect`, `disconnect`, `is_connected`, `get_account_info`, `get_symbol_info`, `get_candles`, `place_order`, `close_position`, `get_open_positions`)
    - Create `src/forex_signals/broker/models.py` with `AccountInfo`, `SymbolInfo`, `Position`, `TradeExecutionResult`, `BrokerType`
    - _Requirements: FR7.1, FR7.2, NFR1_

  - [x] 8.2 Create MQL5 Expert Advisor script (`ForexBridge.mq5`)
    - Create `scripts/mt5/ForexBridge.mq5` script running inside MT5 on Mac
    - Open TCP server socket on `127.0.0.1:<port>` (default: 5555)
    - Implement command handlers for `PING`, `ACCOUNT_INFO`, `SYMBOL_INFO`, `GET_CANDLES`, `ORDER_SEND`, `ORDER_CLOSE`, `GET_POSITIONS`
    - Serialize responses in newline-delimited JSON
    - _Requirements: FR7.1, FR7.2, FR7.3, FR7.4, FR7.5_

  - [x] 8.3 Implement `SocketBrokerClient` in Python
    - Create `src/forex_signals/broker/socket_client.py` connecting via standard TCP socket to `127.0.0.1:5555`
    - Implement JSON request serialization, response parsing, and error code handling
    - Implement automatic reconnection with exponential backoff on connection drops
    - _Requirements: FR7.1, NFR2, NFR4, NFR6_

  - [x] 8.4 Implement `MockBrokerClient` for offline testing & CI
    - Create `src/forex_signals/broker/mock.py` simulating broker execution in pure Python
    - Track simulated balance, positions, fills, and stop-loss/take-profit triggers
    - _Requirements: FR7.6, FR8.4, NFR5_

  - [x] 8.5 Implement symbol validation, lot quantization, and spread guardrail
    - Normalize symbol names and query broker digits/point
    - Quantize lot size to `lot_step` within `[min_lot, max_lot]`
    - Enforce broker `stoplevel` distance on SL/TP calculations
    - Implement pre-trade spread filter: reject order if live spread > `max_spread_pips`
    - _Requirements: FR7.2, FR7.4, FR7.6_

  - [x] 8.6 Implement live trading engine loop
    - Create `src/forex_signals/broker/live_runner.py` with `LiveTradingEngine`
    - Synchronize execution loop to candle close intervals
    - Fetch candles -> evaluate 5 strategies -> consensus -> position checks -> order placement
    - Log real-time trade events, P&L, and account equity
    - _Requirements: FR7.3, FR7.5, NFR6_

  - [x] 8.7* Write property tests for MT5 trade calculations and safety guardrails
    - **Property 11: MT5 SL/TP distance and minimum stop level compliance** (_Validates: FR7.4_)
    - **Property 12: MT5 lot size quantization** (_Validates: FR7.2_)
    - **Property 13: Spread filter order gatekeeping** (_Validates: FR7.6_)
    - **Property 14: MT5 order ticket tracking and bot isolation** (_Validates: FR7.4, FR7.5_)

  - [x] 8.8 Write unit and integration tests for socket client and mock broker
    - Test `SocketBrokerClient` request/response framing with a mock TCP server
    - Test `MockBrokerClient` order placement, position query, and closing
    - Test spread filter rejection, stop-level validation, and reconnection backoff
    - _Requirements: FR7, FR8.4_

- [x] 9. CLI integration & wiring
  - [x] 9.1 Wire backtest CLI command with config and auto-tuning
    - `forex-signals backtest` CLI command supporting all strategy parameters, CSV export, and `--auto-tune` flag
    - _Requirements: FR1, FR2, FR3, FR4, FR5, FR6, NFR3_

  - [x] 9.2 Implement `live` CLI command for MT5 execution
    - Add `forex-signals live` CLI command with options: `--host`, `--port`, `--mock/--no-mock`, `--pair`, `--lot-size`, `--magic-number`, `--max-spread`
    - Connect to socket bridge or mock broker, run live loop, handle graceful Ctrl+C shutdown
    - _Requirements: FR7, NFR2, NFR3_

- [x] 10. Final Verification & Checkpoint
  - [x] 10.1 Run entire test suite (unit tests, property tests, broker mock integration tests)
  - [x] 10.2 Verify backtest CLI, auto-tune CLI, and live broker simulation CLI commands
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are property-based tests validating formal correctness properties from the design document.
- Checkpoints ensure incremental validation.
- **Method A (Local TCP Socket Bridge)** allows running native macOS Python code communicating with MT5 on Mac over `127.0.0.1:5555` with zero Wine command friction.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["1.5", "2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "5.1"] },
    { "id": 4, "tasks": ["2.7", "2.8", "3.2", "3.3", "3.4", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "6.4", "6.5", "6.6", "6.7"] },
    { "id": 7, "tasks": ["6.8", "7.1"] },
    { "id": 8, "tasks": ["7.2", "8.1", "8.2", "8.4"] },
    { "id": 9, "tasks": ["8.3", "8.5", "8.6"] },
    { "id": 10, "tasks": ["8.7", "8.8", "9.1", "9.2"] },
    { "id": 11, "tasks": ["10.1", "10.2"] }
  ]
}
```
