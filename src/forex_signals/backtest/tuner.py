"""Auto-tuning utilities for backtesting configuration."""

import csv
import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import click

from forex_signals.backtest.engine import BacktestEngine
from forex_signals.backtest.metrics import MetricsCalculator
from forex_signals.consensus.engine import ConsensusEngine
from forex_signals.data.models import Candle, Order
from forex_signals.orders.manager import OrderManager
from forex_signals.strategies import (
    BollingerBandsStrategy,
    MACDStrategy,
    MovingAverageCrossoverStrategy,
    RSIStrategy,
    SMIStrategy,
)


@dataclass(frozen=True)
class TuningResult:
    """Result of an auto-tuning run."""

    consensus_threshold: int
    strategy_params: Dict[str, Dict[str, Any]]
    score: float


class AutoTuningEngine:
    """Search a small grid of backtest configurations and select the best one."""

    def __init__(
        self,
        strategies: List[Any],
        order_manager: OrderManager,
        train_split: float = 0.7,
        consensus_threshold_values: Optional[List[int]] = None,
        strategy_param_values: Optional[Dict[str, Dict[str, List[Any]]]] = None,
        output_path: Optional[str] = None,
    ):
        self.strategies = strategies
        self.order_manager = order_manager
        self.train_split = train_split
        self.consensus_threshold_values = consensus_threshold_values or [2, 3, 4, 5]
        self.strategy_param_values = strategy_param_values or {}
        self.output_path = output_path

    def tune(self, candles: List[Candle]) -> TuningResult:
        """Evaluate candidate configurations on a training slice and return the best."""
        if not candles:
            return TuningResult(consensus_threshold=1, strategy_params={}, score=0.0)

        split_index = max(1, int(len(candles) * self.train_split))
        train_candles = candles[:split_index]
        candidate_count = 0

        for threshold in self.consensus_threshold_values:
            candidate_count += len(self._generate_parameter_combinations(self._base_strategy_params()))

        click.echo("Auto-tuning started. Searching for the best parameter set...")
        click.echo(f"Starting auto-tuning over {candidate_count} candidate configurations on {len(train_candles)} training candles...")

        best_result: Optional[TuningResult] = None
        best_score = float("-inf")

        completed_signatures = self._load_completed_signatures()
        base_params = self._base_strategy_params()
        candidate_rows: List[Dict[str, Any]] = []
        total_candidates = 0
        for threshold in self.consensus_threshold_values:
            for candidate_params in self._generate_parameter_combinations(base_params):
                total_candidates += 1
                candidate_signature = self._signature_for_candidate(threshold, candidate_params)
                if candidate_signature in completed_signatures:
                    click.echo(
                        f"Skipping already-completed candidate {total_candidates}/{candidate_count}: threshold={threshold}, params={candidate_params}"
                    )
                    continue

                click.echo(
                    f"Evaluating candidate {total_candidates}/{candidate_count}: threshold={threshold}, params={candidate_params}"
                )
                engine = BacktestEngine(
                    strategies=self._build_strategies(candidate_params),
                    consensus=ConsensusEngine(threshold=threshold),
                    order_manager=self.order_manager,
                )
                result = engine.run(train_candles)
                score = self._score_result(result)
                candidate_entry = {
                    "score": score,
                    "max_drawdown": result.max_drawdown,
                    "win_rate": result.win_rate,
                    "consensus_threshold": threshold,
                    **self._flatten_strategy_params(candidate_params),
                }
                candidate_rows.append(candidate_entry)
                self._append_candidate_result(candidate_entry)
                completed_signatures.add(candidate_signature)
                if score > best_score:
                    best_score = score
                    best_result = TuningResult(
                        consensus_threshold=threshold,
                        strategy_params=candidate_params,
                        score=score,
                    )
                    click.echo(
                        f"  New best candidate: threshold={threshold}, score={score:.4f}, params={candidate_params}"
                    )

        if self.output_path:
            click.echo(f"Auto-tuning results written to {self.output_path}")

        if best_result is None:
            return TuningResult(consensus_threshold=1, strategy_params=base_params, score=0.0)

        return best_result

    def _base_strategy_params(self) -> Dict[str, Dict[str, Any]]:
        params: Dict[str, Dict[str, Any]] = {}
        for strategy in self.strategies:
            strategy_key = self._strategy_key(strategy)
            if strategy_key:
                params[strategy_key] = self._strategy_defaults(strategy)
        return params

    def _strategy_key(self, strategy: Any) -> Optional[str]:
        if isinstance(strategy, SMIStrategy):
            return "smi"
        if isinstance(strategy, MovingAverageCrossoverStrategy):
            return "moving_average"
        if isinstance(strategy, RSIStrategy):
            return "rsi"
        if isinstance(strategy, MACDStrategy):
            return "macd"
        if isinstance(strategy, BollingerBandsStrategy):
            return "bollinger"
        return None

    def _strategy_defaults(self, strategy: Any) -> Dict[str, Any]:
        if isinstance(strategy, SMIStrategy):
            return {"period": strategy._period, "smooth_period": strategy._smooth_period}
        if isinstance(strategy, MovingAverageCrossoverStrategy):
            return {"fast_period": strategy._fast_period, "slow_period": strategy._slow_period}
        if isinstance(strategy, RSIStrategy):
            return {
                "period": strategy._period,
                "overbought": strategy._overbought,
                "oversold": strategy._oversold,
            }
        if isinstance(strategy, MACDStrategy):
            return {
                "fast_period": strategy._fast_period,
                "slow_period": strategy._slow_period,
                "signal_period": strategy._signal_period,
            }
        if isinstance(strategy, BollingerBandsStrategy):
            return {"period": strategy._period, "std_dev": strategy._std_dev}
        return {}

    def _load_completed_signatures(self) -> set:
        if not self.output_path or not os.path.exists(self.output_path):
            return set()

        completed: set = set()
        try:
            with open(self.output_path, newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    threshold = row.get("consensus_threshold")
                    if not threshold:
                        continue
                    params = {
                        key: value
                        for key, value in row.items()
                        if key not in {"score", "max_drawdown", "win_rate", "consensus_threshold"}
                    }
                    completed.add(self._signature_from_row(int(threshold), params))
        except OSError:
            return set()
        return completed

    def _signature_for_candidate(self, threshold: int, strategy_params: Dict[str, Dict[str, Any]]) -> Tuple[str, ...]:
        flattened = self._flatten_strategy_params(strategy_params)
        return (str(threshold),) + tuple(sorted(f"{k}={flattened[k]}" for k in flattened))

    def _signature_from_row(self, threshold: int, params: Dict[str, str]) -> Tuple[str, ...]:
        return (str(threshold),) + tuple(sorted(f"{k}={params[k]}" for k in params))

    def _flatten_strategy_params(self, strategy_params: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        flattened: Dict[str, Any] = {}
        for strategy_name, params in strategy_params.items():
            for param_name, value in params.items():
                flattened[f"{strategy_name}.{param_name}"] = value
        return flattened

    def _append_candidate_result(self, candidate_entry: Dict[str, Any]) -> None:
        if not self.output_path:
            return

        output_dir = os.path.dirname(self.output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        file_exists = os.path.exists(self.output_path)
        fieldnames = ["score", "consensus_threshold"]
        fieldnames.extend(sorted(k for k in candidate_entry.keys() if k not in fieldnames))

        with open(self.output_path, "a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(candidate_entry)

    def _generate_parameter_combinations(
        self, base_params: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Dict[str, Any]]]:
        if not self.strategy_param_values:
            return [deepcopy(base_params)]

        candidates: List[Dict[str, Dict[str, Any]]] = [deepcopy(base_params)]
        for strategy_name, param_values in self.strategy_param_values.items():
            if strategy_name not in base_params:
                continue
            new_candidates: List[Dict[str, Dict[str, Any]]] = []
            for candidate in candidates:
                for param_name, values in param_values.items():
                    for value in values:
                        updated = deepcopy(candidate)
                        updated[strategy_name][param_name] = value
                        new_candidates.append(updated)
            candidates = new_candidates or candidates
        return candidates

    def _build_strategies(self, strategy_params: Dict[str, Dict[str, Any]]) -> List[Any]:
        strategy_instances: List[Any] = []
        for strategy in self.strategies:
            strategy_name = self._strategy_key(strategy)
            if strategy_name in {"smi", "moving_average", "rsi", "macd", "bollinger"}:
                params = strategy_params.get(strategy_name, {})
                if strategy_name == "smi":
                    strategy_instances.append(
                        SMIStrategy(
                            period=params.get("period", 14),
                            smooth_period=params.get("smooth_period", 3),
                        )
                    )
                elif strategy_name == "moving_average":
                    strategy_instances.append(
                        MovingAverageCrossoverStrategy(
                            fast_period=params.get("fast_period", 10),
                            slow_period=params.get("slow_period", 50),
                        )
                    )
                elif strategy_name == "rsi":
                    strategy_instances.append(
                        RSIStrategy(
                            period=params.get("period", 14),
                            overbought=params.get("overbought", 70),
                            oversold=params.get("oversold", 30),
                        )
                    )
                elif strategy_name == "macd":
                    strategy_instances.append(
                        MACDStrategy(
                            fast_period=params.get("fast_period", 12),
                            slow_period=params.get("slow_period", 26),
                            signal_period=params.get("signal_period", 9),
                        )
                    )
                elif strategy_name == "bollinger":
                    strategy_instances.append(
                        BollingerBandsStrategy(
                            period=params.get("period", 20),
                            std_dev=params.get("std_dev", 2.0),
                        )
                    )
            else:
                strategy_instances.append(strategy)
        return strategy_instances

    def _score_result(self, result: Any) -> float:
        if result.num_trades == 0:
            return -1.0
        sharpe = result.sharpe_ratio
        if sharpe != 0.0:
            return sharpe
        return result.profit_factor
