from __future__ import annotations

from engine.strategy.base import Strategy
from engine.strategy.mean_reversion import MeanReversionStrategy
from engine.strategy.ml_models import LinearRegressionStrategy, LogisticRegressionStrategy
from engine.strategy.moving_average import MovingAverageCrossStrategy


SUPPORTED_STRATEGIES = {
    "moving_average": MovingAverageCrossStrategy,
    "mean_reversion": MeanReversionStrategy,
    "linear_regression": LinearRegressionStrategy,
    "logistic_regression": LogisticRegressionStrategy,
}


def create_strategy(strategy_name: str, symbols: list[str]) -> Strategy:
    normalized = strategy_name.lower()
    strategy_cls = SUPPORTED_STRATEGIES.get(normalized)
    if strategy_cls is None:
        available = ", ".join(sorted(SUPPORTED_STRATEGIES))
        raise ValueError(f"Unsupported strategy '{strategy_name}'. Available: {available}")
    return strategy_cls(symbols=symbols)
