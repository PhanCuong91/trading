# Implementation Plan: Forex Trading Signal System

## Overview

Build a Python forex trading signal system with a pipeline architecture: Data Source → Strategy Engine → Consensus → Order Manager → Backtest Engine. Implementation proceeds bottom-up from data models and configuration through individual strategies, consensus logic, order management, backtesting, and finally CLI wiring.

## Tasks

- [x] 1. Set up project structure, data models, and configuration
  - [x] 1.1 Create project skeleton with pyproject.toml and package structure
    - Create `pyproject.toml` with dependencies (yfinance, pandas, numpy, pyyaml, click)
    - Create `src/forex_signals/__init__.py` and all subpackage `__init__.py` files
    - Create directory structure: `data/`, `strategies/`, `consensus/`, `orders/`, `backtest/`, `broker/`
    - Create `tests/conftest.py` and test subdirectories
    - Create default `config.yaml` with all strategy parameters
    - _Requirements: NFR (modular package structure, configurable)_

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
    - _Requirements: NFR (configurable), FR1.3_

  - [x] 1.4 Implement Yahoo Finance data downloader
    - Create `src/forex_signals/data/downloader.py` with `YahooDataDownloader` class
    - Download OHLC data using yfinance, convert to `List[Candle]`
    - Implement retry with exponential backoff (3 attempts)
    - Raise `DataDownloadError` on failure
    - Detect and log data gaps
    - _Requirements: FR1.1, FR1.2, FR1.3_

- [ ] 2. Implement trading strategies
  - [x] 2.1 Implement strategy base protocol
    - Create `src/forex_signals/strategies/base.py` with `Strategy` Protocol
    - Define `name`, `generate_signal(candles)`, and `min_candles` interface
    - _Requirements: FR2, NFR (extensibility)_

  - [x] 2.2 Implement SMI strategy
    - Create `src/forex_signals/strategies/smi.py`
    - Calculate distance from close to midpoint of high-low range
    - Double EMA smoothing with configurable period and smooth_period
    - BUY on SMI crossing above -40, SELL on crossing below +40
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.1_

  - [ ] 2.3 Implement Moving Average crossover strategy
    - Create `src/forex_signals/strategies/moving_average.py`
    - Configurable fast_period (default 10) and slow_period (default 50)
    - BUY on golden cross, SELL on death cross, NEUTRAL otherwise
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.2_

  - [ ] 2.4 Implement RSI strategy
    - Create `src/forex_signals/strategies/rsi.py`
    - Standard 14-period RSI calculation
    - BUY when RSI crosses above oversold (30), SELL when crosses below overbought (70)
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.3_

  - [ ] 2.5 Implement MACD strategy
    - Create `src/forex_signals/strategies/macd.py`
    - Standard MACD (12, 26, 9) calculation
    - BUY on MACD crossing above signal, SELL on crossing below
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.4_

  - [ ] 2.6 Implement Bollinger Bands strategy
    - Create `src/forex_signals/strategies/bollinger.py`
    - 20-period SMA with configurable std_dev bands
    - BUY on price touching/crossing below lower band and reversing
    - SELL on price touching/crossing above upper band and reversing
    - Return NEUTRAL if insufficient candles
    - _Requirements: FR2.5_

  - [ ]* 2.7 Write property test for strategy signal validity
    - **Property 1: Strategy signal validity**
    - For any valid candle sequence with sufficient length and for any strategy, `generate_signal` returns exactly BUY, SELL, or NEUTRAL without raising
    - **Validates: Requirements FR2.1, FR2.2, FR2.3, FR2.4, FR2.5**

  - [ ]* 2.8 Write unit tests for all strategies
    - Test each strategy with known price patterns that produce expected signals
    - Test NEUTRAL output when insufficient candles provided
    - Test edge cases (flat prices, extreme values)
    - _Requirements: FR2, FR6.1_

- [ ] 3. Implement consensus engine
  - [ ] 3.1 Implement consensus engine logic
    - Create `src/forex_signals/consensus/engine.py` with `ConsensusEngine` class
    - Configurable threshold (default 4)
    - Count BUY and SELL signals; return direction if count >= threshold, else NEUTRAL
    - _Requirements: FR3.1, FR3.2, FR3.3_

  - [ ]* 3.2 Write property test for consensus threshold correctness
    - **Property 2: Consensus threshold correctness**
    - For any list of 5 signals, consensus returns BUY iff >=4 are BUY, SELL iff >=4 are SELL, NEUTRAL otherwise
    - **Validates: Requirements FR3.2, FR3.3**

  - [ ]* 3.3 Write property test for consensus symmetry
    - **Property 3: Consensus symmetry (equal weight)**
    - For any list of 5 signals and any permutation, consensus produces the same result
    - **Validates: Requirements FR3.1**

  - [ ]* 3.4 Write integration tests for consensus engine
    - Test consensus with mixed signals below threshold → NEUTRAL
    - Test consensus with 4 BUY + 1 SELL → BUY
    - Test consensus with 4 SELL + 1 NEUTRAL → SELL
    - Test with all 5 agreeing → signal matches
    - _Requirements: FR3, FR6.2_

- [ ] 4. Checkpoint - Ensure strategies and consensus tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement order management
  - [ ] 5.1 Implement Order models and OrderManager
    - Create `src/forex_signals/orders/models.py` (if separate from data models)
    - Create `src/forex_signals/orders/manager.py` with `OrderManager` class
    - `create_order`: calculate SL/TP prices from pips and pip_value (0.0001)
    - `update_order`: check candle high/low against SL/TP levels, close if hit
    - Track PnL on close
    - _Requirements: FR4.1, FR4.2, FR4.3, FR4.4_

  - [ ]* 5.2 Write property test for SL/TP price calculation
    - **Property 4: Stop-loss and take-profit price calculation**
    - For any entry price and positive SL/TP pips: BUY → SL < entry < TP; SELL → TP < entry < SL
    - Distance from entry equals pips * pip_value
    - **Validates: Requirements FR4.2, FR4.3**

  - [ ]* 5.3 Write property test for order lifecycle state machine
    - **Property 5: Order lifecycle state machine**
    - Open order closes iff candle price range intersects SL or TP; once closed, status never changes
    - **Validates: Requirements FR4.4**

  - [ ]* 5.4 Write unit tests for order management
    - Test BUY order creation with correct SL/TP
    - Test SELL order creation with correct SL/TP
    - Test order closed by TP (candle high hits TP for BUY)
    - Test order closed by SL (candle low hits SL for BUY)
    - Test order remains open when candle doesn't hit SL/TP
    - _Requirements: FR4, FR6_

- [ ] 6. Implement backtest engine and metrics
  - [ ] 6.1 Implement metrics calculator
    - Create `src/forex_signals/backtest/metrics.py` with `MetricsCalculator` class
    - Implement: `win_rate`, `total_pnl`, `max_drawdown`, `sharpe_ratio`, `profit_factor`, `avg_trade_duration`
    - Handle edge cases: empty trades, zero std dev, no losing trades
    - _Requirements: FR5.2, FR5.3, FR5.4, FR5.5, FR5.6, FR5.7_

  - [ ]* 6.2 Write property test for win rate metric
    - **Property 6: Win rate metric correctness**
    - For any non-empty list of closed trades, win rate = count(pnl > 0) / total, always in [0.0, 1.0]
    - **Validates: Requirements FR5.2**

  - [ ]* 6.3 Write property test for max drawdown
    - **Property 7: Max drawdown non-negativity and correctness**
    - For any sequence of trades, max drawdown >= 0 and equals max peak-to-trough in cumulative PnL
    - **Validates: Requirements FR5.4**

  - [ ]* 6.4 Write property test for profit factor
    - **Property 8: Profit factor correctness**
    - Profit factor = gross_profit / abs(gross_loss); inf if no losers, 0.0 if no winners
    - **Validates: Requirements FR5.6**

  - [ ]* 6.5 Write property test for total PnL additivity
    - **Property 9: Total PnL additivity**
    - total_pnl(A + B) == total_pnl(A) + total_pnl(B) for any partition
    - **Validates: Requirements FR5.3**

  - [ ]* 6.6 Write property test for Sharpe ratio
    - **Property 10: Sharpe ratio formula correctness**
    - For 2+ trades with non-zero std: sharpe = (mean - rfr) / std; otherwise 0.0
    - **Validates: Requirements FR5.5**

  - [ ] 6.7 Implement backtest engine orchestrator
    - Create `src/forex_signals/backtest/engine.py` with `BacktestEngine` class
    - Process candles sequentially: generate signals → consensus → create order if signal and no open position → update open orders
    - After all candles, compute and return `BacktestResult`
    - _Requirements: FR5.1_

  - [ ]* 6.8 Write unit tests for backtest engine
    - Test with known data producing predictable trades
    - Validate metrics match manual calculations
    - Test no-trade scenario (never reaches consensus)
    - _Requirements: FR5, FR6.3_

- [ ] 7. Checkpoint - Ensure all core logic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement broker protocol and CLI
  - [ ] 8.1 Implement broker protocol for future MT5 integration
    - Create `src/forex_signals/broker/base.py` with `Broker` Protocol
    - Define `place_order`, `get_open_orders`, `close_order` interface
    - No concrete implementation needed (future phase)
    - _Requirements: NFR (MT5 integration architecture)_

  - [ ] 8.2 Implement CLI entry point
    - Create `src/forex_signals/cli.py` using click
    - `backtest` command: load config, download data, run backtest, display results
    - CLI options for pair, timeframe, sl-pips, tp-pips, start-date, end-date
    - Pretty-print backtest results (metrics table)
    - Register as console_scripts entry point in pyproject.toml
    - _Requirements: NFR (configurable, CLI)_

  - [ ] 8.3 Wire all components together in backtest command
    - Instantiate all 5 strategies with config parameters
    - Create ConsensusEngine, OrderManager, BacktestEngine
    - Download data → run backtest → display results
    - Handle errors gracefully with user-friendly messages
    - _Requirements: FR1, FR2, FR3, FR4, FR5_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The broker protocol (8.1) is a placeholder for future MT5 integration — only the interface is created
- All strategies return NEUTRAL when insufficient data is available (graceful degradation)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "5.1"] },
    { "id": 4, "tasks": ["2.7", "2.8", "3.2", "3.3", "3.4", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "6.4", "6.5", "6.6", "6.7"] },
    { "id": 7, "tasks": ["6.8", "8.1"] },
    { "id": 8, "tasks": ["8.2"] },
    { "id": 9, "tasks": ["8.3"] }
  ]
}
```
