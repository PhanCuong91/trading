"""Tests for the auto-tuning engine."""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from forex_signals.backtest.tuner import AutoTuningEngine
from forex_signals.data.models import Candle
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies.smi import SMIStrategy


def _make_candles(count: int = 80) -> List[Candle]:
    candles: List[Candle] = []
    price = 1.1000
    for i in range(count):
        price += 0.0001
        candles.append(
            Candle(
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
                open=price,
                high=price + 0.0005,
                low=price - 0.0005,
                close=price,
                volume=1000.0,
            )
        )
    return candles


def test_tune_writes_candidate_results_to_csv(tmp_path):
    output_path = tmp_path / "auto_tune_results.csv"
    candles = _make_candles(80)
    engine = AutoTuningEngine(
        strategies=[SMIStrategy(period=14, smooth_period=3)],
        order_manager=OrderManager(sl_pips=20, tp_pips=40),
        train_split=0.7,
        consensus_threshold_values=[2],
        strategy_param_values={"smi": {"period": [7, 14]}},
        output_path=str(output_path),
    )

    result = engine.tune(candles)

    assert output_path.exists()
    with output_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) >= 2
    assert rows[0]["consensus_threshold"] == "2"
    assert "score" in rows[0]
    assert "max_drawdown" in rows[0]
    assert "win_rate" in rows[0]
    assert rows[0]["smi.period"] in {"7", "14"}
    assert result.consensus_threshold == 2


def test_tune_skips_already_completed_candidates(tmp_path):
    output_path = tmp_path / "auto_tune_results.csv"
    output_path.write_text(
        "score,max_drawdown,win_rate,consensus_threshold,smi.period,smi.smooth_period\n"
        "1.0,0.0,1.0,2,7,3\n"
    )

    candles = _make_candles(80)
    engine = AutoTuningEngine(
        strategies=[SMIStrategy(period=14, smooth_period=3)],
        order_manager=OrderManager(sl_pips=20, tp_pips=40),
        train_split=0.7,
        consensus_threshold_values=[2],
        strategy_param_values={"smi": {"period": [7]}},
        output_path=str(output_path),
    )

    engine.tune(candles)

    with output_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1


def test_tune_emits_progress_messages(capsys):
    candles = _make_candles(80)
    engine = AutoTuningEngine(
        strategies=[SMIStrategy(period=14, smooth_period=3)],
        order_manager=OrderManager(sl_pips=20, tp_pips=40),
        train_split=0.7,
        consensus_threshold_values=[2],
        strategy_param_values={"smi": {"period": [7]}},
    )

    engine.tune(candles)

    captured = capsys.readouterr()
    assert "Starting auto-tuning" in captured.out
    assert "Evaluating candidate" in captured.out
