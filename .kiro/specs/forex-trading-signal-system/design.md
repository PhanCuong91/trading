# Design Document: Forex Trading Signal System

## Architecture Overview

The system follows a pipeline architecture with clear separation between data acquisition, signal generation, consensus decision-making, order management, and performance analysis. Each component is a standalone module with well-defined interfaces, enabling independent testing and future extension (e.g., MT5 integration, new strategies).

```
┌─────────────┐    ┌─────────────────┐    ┌───────────────┐    ┌──────────────┐    ┌─────────────┐
│ Data Source  │───▶│ Strategy Engine  │───▶│   Consensus   │───▶│    Order     │───▶│  Backtest   │
│  (Yahoo)    │    │  (5 strategies) │    │    Engine      │    │   Manager    │    │   Engine    │
└─────────────┘    └─────────────────┘    └───────────────┘    └──────────────┘    └─────────────┘
       ▲                                                                                    │
       │                    ┌──────────────┐                                                │
       └────────────────────│    Config    │◀───────────────────────────────────────────────┘
                            └──────────────┘                              (metrics output)
```

## Package Structure

```
trade/
├── pyproject.toml
├── config.yaml                  # Default configuration
├── src/
│   └── forex_signals/
│       ├── __init__.py
│       ├── cli.py               # CLI entry point
│       ├── config.py            # Configuration loading & validation
│       ├── data/
│       │   ├── __init__.py
│       │   ├── models.py        # Candle, OHLC data models
│       │   └── downloader.py    # Yahoo Finance data fetcher
│       ├── strategies/
│       │   ├── __init__.py
│       │   ├── base.py          # Strategy protocol/ABC
│       │   ├── smi.py           # Stochastic Momentum Index
│       │   ├── moving_average.py # MA crossover
│       │   ├── rsi.py           # Relative Strength Index
│       │   ├── macd.py          # MACD
│       │   └── bollinger.py     # Bollinger Bands
│       ├── consensus/
│       │   ├── __init__.py
│       │   └── engine.py        # Consensus logic
│       ├── orders/
│       │   ├── __init__.py
│       │   ├── models.py        # Order, Position data models
│       │   └── manager.py       # Order lifecycle management
│       ├── backtest/
│       │   ├── __init__.py
│       │   ├── engine.py        # Backtesting orchestrator
│       │   └── metrics.py       # Performance metric calculations
│       └── broker/
│           ├── __init__.py
│           └── base.py          # Broker protocol (for future MT5)
└── tests/
    ├── conftest.py
    ├── test_strategies/
    ├── test_consensus/
    ├── test_orders/
    ├── test_backtest/
    └── test_metrics/
```

## Data Models

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional


class Timeframe(Enum):
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class OrderStatus(Enum):
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class StrategySignal:
    strategy_name: str
    signal: Signal
    timestamp: datetime


@dataclass
class Order:
    direction: Signal  # BUY or SELL only
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.OPEN
    pnl: Optional[float] = None


@dataclass(frozen=True)
class BacktestConfig:
    pair: str
    timeframe: Timeframe
    sl_pips: float
    tp_pips: float
    start_date: datetime
    end_date: datetime


@dataclass(frozen=True)
class BacktestResult:
    trades: List[Order]
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float
    avg_trade_duration_seconds: float
    num_trades: int
```

## Component Interfaces

### Strategy Protocol

```python
from typing import Protocol, List

class Strategy(Protocol):
    """All strategies implement this interface."""

    @property
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Given a sequence of historical candles (most recent last),
        produce a BUY, SELL, or NEUTRAL signal.

        Requires: len(candles) >= self.min_candles
        Returns: Signal enum value
        """
        ...

    @property
    def min_candles(self) -> int:
        """Minimum number of candles required to produce a signal."""
        ...
```

### Consensus Engine

```python
class ConsensusEngine:
    """Determines trade signal from strategy agreement."""

    def __init__(self, threshold: int = 4):
        """
        Args:
            threshold: Minimum number of strategies that must agree.
                       Default is 4 out of 5.
        """
        self.threshold = threshold

    def evaluate(self, signals: List[StrategySignal]) -> Signal:
        """
        Count BUY and SELL signals. If either count >= threshold,
        return that direction. Otherwise return NEUTRAL.

        Args:
            signals: List of strategy signals (one per strategy)

        Returns:
            Signal.BUY, Signal.SELL, or Signal.NEUTRAL
        """
        ...
```

### Order Manager

```python
class OrderManager:
    """Creates and manages order lifecycle."""

    def __init__(self, sl_pips: float, tp_pips: float, pip_value: float = 0.0001):
        ...

    def create_order(self, direction: Signal, entry_price: float, entry_time: datetime) -> Order:
        """
        Create an order with calculated SL and TP prices.

        For BUY: SL = entry - sl_pips * pip_value, TP = entry + tp_pips * pip_value
        For SELL: SL = entry + sl_pips * pip_value, TP = entry - tp_pips * pip_value
        """
        ...

    def update_order(self, order: Order, candle: Candle) -> Order:
        """
        Check if the given candle triggers SL or TP.
        Returns updated order (possibly closed).
        """
        ...
```

### Backtest Engine

```python
class BacktestEngine:
    """Orchestrates backtesting across historical data."""

    def __init__(
        self,
        strategies: List[Strategy],
        consensus: ConsensusEngine,
        order_manager: OrderManager,
    ):
        ...

    def run(self, candles: List[Candle]) -> BacktestResult:
        """
        Process candles sequentially:
        1. For each candle, generate signals from all strategies
        2. Evaluate consensus
        3. If signal and no open position, create order
        4. Update open orders against current candle
        5. After all candles, compute metrics
        """
        ...
```

### Metrics Calculator

```python
class MetricsCalculator:
    """Pure functions for computing backtest performance metrics."""

    @staticmethod
    def win_rate(trades: List[Order]) -> float:
        """Winning trades / total trades. Returns 0.0 if no trades."""
        ...

    @staticmethod
    def total_pnl(trades: List[Order]) -> float:
        """Sum of all trade PnLs."""
        ...

    @staticmethod
    def max_drawdown(trades: List[Order]) -> float:
        """
        Maximum peak-to-trough decline in cumulative equity.
        Returns a non-negative value (0 means no drawdown).
        """
        ...

    @staticmethod
    def sharpe_ratio(trades: List[Order], risk_free_rate: float = 0.0) -> float:
        """
        (mean_return - risk_free_rate) / std_return.
        Returns 0.0 if fewer than 2 trades or zero std.
        """
        ...

    @staticmethod
    def profit_factor(trades: List[Order]) -> float:
        """
        Gross profit / gross loss. Returns inf if no losing trades,
        0.0 if no winning trades.
        """
        ...

    @staticmethod
    def avg_trade_duration(trades: List[Order]) -> float:
        """Average duration in seconds across all closed trades."""
        ...
```

### Data Downloader

```python
class YahooDataDownloader:
    """Downloads OHLC data from Yahoo Finance."""

    def download(self, pair: str, timeframe: Timeframe,
                 start: datetime, end: datetime) -> List[Candle]:
        """
        Fetch candlestick data from Yahoo Finance.

        Args:
            pair: Forex pair symbol (e.g., "EURUSD=X")
            timeframe: Candle timeframe
            start: Start datetime
            end: End datetime

        Returns:
            List of Candle objects, sorted by timestamp ascending
        """
        ...
```

### Broker Protocol (Future MT5 Integration)

```python
class Broker(Protocol):
    """Abstract broker interface for future live trading."""

    def place_order(self, order: Order) -> str:
        """Place order, return order ID."""
        ...

    def get_open_orders(self) -> List[Order]:
        ...

    def close_order(self, order_id: str) -> Order:
        ...
```

## Configuration

```yaml
# config.yaml
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
```

## Strategy Details

### SMI (Stochastic Momentum Index)
- Calculates the distance of close from the midpoint of the high-low range
- Smoothed with double EMA
- BUY when SMI crosses above -40 (oversold recovery)
- SELL when SMI crosses below +40 (overbought reversal)
- NEUTRAL otherwise

### Moving Average Crossover
- Fast MA (default 10-period) and Slow MA (default 50-period)
- BUY when fast crosses above slow (golden cross)
- SELL when fast crosses below slow (death cross)
- NEUTRAL when no crossover on current candle

### RSI (Relative Strength Index)
- Standard 14-period RSI calculation
- BUY when RSI crosses above oversold level (30)
- SELL when RSI crosses below overbought level (70)
- NEUTRAL otherwise

### MACD
- Standard MACD (12, 26, 9)
- BUY when MACD line crosses above signal line
- SELL when MACD line crosses below signal line
- NEUTRAL when no crossover

### Bollinger Bands
- 20-period SMA with 2 standard deviation bands
- BUY when price touches/crosses below lower band and reverses
- SELL when price touches/crosses above upper band and reverses
- NEUTRAL otherwise

## Error Handling

- **Insufficient data**: Strategies return NEUTRAL when fewer than `min_candles` are available
- **Network failures**: Data downloader retries with exponential backoff (3 attempts), raises `DataDownloadError` on failure
- **Invalid configuration**: Config loader validates all values at startup, raises `ConfigError` with descriptive message
- **Division by zero in metrics**: Handled gracefully (0.0 for empty trade lists, inf for zero denominators where appropriate)
- **Yahoo Finance data gaps**: Missing candles are detected and logged; backtester skips gaps rather than interpolating

## Extensibility Points

1. **New strategies**: Implement `Strategy` protocol, register in config
2. **New pairs**: Add pair to config, downloader handles any Yahoo Finance symbol
3. **ATR-based SL/TP**: Extend `OrderManager` with `DynamicStopLoss` protocol
4. **MT5 integration**: Implement `Broker` protocol with MT5 connection
5. **Weighted consensus**: Extend `ConsensusEngine` with optional weight parameter

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Strategy signal validity

*For any* valid OHLC candle sequence with sufficient length and *for any* of the 5 strategies, the `generate_signal` method SHALL return exactly one of `Signal.BUY`, `Signal.SELL`, or `Signal.NEUTRAL` — never raising an exception or returning an invalid value.

**Validates: Requirements FR2.1, FR2.2, FR2.3, FR2.4, FR2.5**

### Property 2: Consensus threshold correctness

*For any* list of 5 strategy signals, the consensus engine SHALL return `Signal.BUY` if and only if at least 4 signals are BUY, SHALL return `Signal.SELL` if and only if at least 4 signals are SELL, and SHALL return `Signal.NEUTRAL` in all other cases.

**Validates: Requirements FR3.2, FR3.3**

### Property 3: Consensus symmetry (equal weight)

*For any* list of 5 strategy signals and *for any* permutation of those signals, the consensus engine SHALL produce the same result — proving that no strategy position in the list receives preferential treatment.

**Validates: Requirements FR3.1**

### Property 4: Stop-loss and take-profit price calculation

*For any* entry price, *for any* positive SL pip value, and *for any* positive TP pip value: for a BUY order, `stop_loss < entry_price < take_profit`; for a SELL order, `take_profit < entry_price < stop_loss`. Furthermore, the distance from entry to SL SHALL equal `sl_pips * pip_value` and entry to TP SHALL equal `tp_pips * pip_value`.

**Validates: Requirements FR4.2, FR4.3**

### Property 5: Order lifecycle state machine

*For any* open order and *for any* subsequent candle, the order SHALL close if and only if the candle's price range intersects the SL or TP level. A BUY order closes at SL if `candle.low <= stop_loss` and closes at TP if `candle.high >= take_profit`. A SELL order closes at SL if `candle.high >= stop_loss` and closes at TP if `candle.low <= take_profit`. Once closed, an order's status SHALL never change again.

**Validates: Requirements FR4.4**

### Property 6: Win rate metric correctness

*For any* non-empty list of closed trades with known PnL values, the win rate SHALL equal the count of trades where `pnl > 0` divided by the total number of trades, and SHALL always be in the range [0.0, 1.0].

**Validates: Requirements FR5.2**

### Property 7: Max drawdown non-negativity and correctness

*For any* sequence of closed trades, the max drawdown SHALL be non-negative. Furthermore, for any equity curve derived from cumulative PnL, the max drawdown SHALL equal the maximum value of `(peak - trough)` where the trough occurs after the peak.

**Validates: Requirements FR5.4**

### Property 8: Profit factor correctness

*For any* list of closed trades, the profit factor SHALL equal `sum(pnl for trades where pnl > 0) / abs(sum(pnl for trades where pnl < 0))`. When there are no losing trades, it SHALL return infinity. When there are no winning trades, it SHALL return 0.0.

**Validates: Requirements FR5.6**

### Property 9: Total PnL additivity

*For any* list of closed trades, the total PnL SHALL equal the sum of individual trade PnLs. Equivalently, for any partition of the trade list into two sublists A and B, `total_pnl(A + B) == total_pnl(A) + total_pnl(B)`.

**Validates: Requirements FR5.3**

### Property 10: Sharpe ratio formula correctness

*For any* list of 2 or more trade returns with non-zero standard deviation, the Sharpe ratio SHALL equal `(mean(returns) - risk_free_rate) / std(returns)`. For fewer than 2 trades or zero standard deviation, it SHALL return 0.0.

**Validates: Requirements FR5.5**
