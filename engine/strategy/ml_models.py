from __future__ import annotations

from collections import deque
from queue import Queue

import numpy as np
import pandas as pd

from engine.events import MarketEvent, SignalEvent
from engine.strategy.base import Strategy
from engine.strategy.features import FEATURE_COLUMNS, build_feature_frame, feature_matrix


class _PredictiveModelStrategy(Strategy):
    history_window = 25
    prediction_threshold = 0.001

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(symbols)
        self.price_history: dict[str, deque[float]] = {
            symbol: deque(maxlen=self.history_window) for symbol in symbols
        }
        self.volume_history: dict[str, deque[float]] = {
            symbol: deque(maxlen=self.history_window) for symbol in symbols
        }
        self.current_regime: dict[str, str] = {symbol: "FLAT" for symbol in symbols}
        self.model_by_symbol: dict[str, np.ndarray] = {}
        self.intercept_by_symbol: dict[str, float] = {}

    def fit(self, training_data: pd.DataFrame) -> dict[str, object]:
        feature_frame = build_feature_frame(training_data)
        self.training_summary = {
            "strategy": self.name,
            "feature_columns": FEATURE_COLUMNS,
            "trained_symbols": [],
        }
        symbols_trained = []
        for symbol in self.symbols:
            symbol_frame = feature_frame.loc[feature_frame["symbol"] == symbol].dropna().reset_index(drop=True)
            if symbol_frame.empty:
                continue
            weights, intercept = self._fit_symbol_model(symbol, symbol_frame)
            self.model_by_symbol[symbol] = weights
            self.intercept_by_symbol[symbol] = intercept
            self.price_history[symbol].clear()
            self.volume_history[symbol].clear()
            warmup = training_data.loc[training_data["symbol"] == symbol].tail(self.history_window)
            self.price_history[symbol].extend(float(value) for value in warmup["close"])
            self.volume_history[symbol].extend(float(value) for value in warmup["volume"])
            self.current_regime[symbol] = "FLAT"
            symbols_trained.append(symbol)

        self.training_summary["trained_symbols"] = symbols_trained
        return self.training_summary

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        if event.symbol not in self.symbols or event.symbol not in self.model_by_symbol:
            return

        prices = self.price_history[event.symbol]
        volumes = self.volume_history[event.symbol]
        prices.append(event.close)
        volumes.append(event.volume)

        if len(prices) < self.history_window or len(volumes) < self.history_window:
            return

        features = self._latest_feature_vector(prices, volumes)
        if features is None:
            return

        raw_signal = self._predict(event.symbol, features)
        next_regime = self._signal_direction(raw_signal)
        current_regime = self.current_regime[event.symbol]
        if next_regime == current_regime:
            return
        if current_regime == "FLAT" and next_regime == "EXIT":
            return

        self.current_regime[event.symbol] = "FLAT" if next_regime == "EXIT" else next_regime
        event_queue.put(
            SignalEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                direction=next_regime,
                strength=min(2.0, abs(raw_signal) * 100.0),
                metadata={
                    "strategy": self.name,
                    "model_output": f"{raw_signal:.6f}",
                },
            )
        )

    def _latest_feature_vector(self, prices: deque[float], volumes: deque[float]) -> np.ndarray | None:
        prices_arr = np.array(prices, dtype=float)
        volumes_arr = np.array(volumes, dtype=float)
        if np.any(prices_arr <= 0):
            return None

        ret_1 = prices_arr[-1] / prices_arr[-2] - 1.0
        ret_3 = prices_arr[-1] / prices_arr[-4] - 1.0
        ret_5 = prices_arr[-1] / prices_arr[-6] - 1.0
        momentum_10 = prices_arr[-1] / prices_arr[-11] - 1.0
        momentum_20 = prices_arr[-1] / prices_arr[-21] - 1.0
        daily_returns = prices_arr[1:] / prices_arr[:-1] - 1.0
        volatility_10 = float(np.std(daily_returns[-10:]))
        volume_window = volumes_arr[-10:]
        volume_std = float(np.std(volume_window))
        volume_z_10 = 0.0 if volume_std == 0 else float((volume_window[-1] - np.mean(volume_window)) / volume_std)

        return np.array(
            [ret_1, ret_3, ret_5, momentum_10, momentum_20, volatility_10, volume_z_10],
            dtype=float,
        )

    def _signal_direction(self, raw_signal: float) -> str:
        if raw_signal > self.prediction_threshold:
            return "LONG"
        if raw_signal < -self.prediction_threshold:
            return "SHORT"
        return "EXIT"

    def _fit_symbol_model(self, symbol: str, symbol_frame: pd.DataFrame) -> tuple[np.ndarray, float]:
        raise NotImplementedError

    def _predict(self, symbol: str, features: np.ndarray) -> float:
        raise NotImplementedError


class LinearRegressionStrategy(_PredictiveModelStrategy):
    name = "linear_regression"
    prediction_threshold = 0.0015

    def _fit_symbol_model(self, symbol: str, symbol_frame: pd.DataFrame) -> tuple[np.ndarray, float]:
        del symbol
        x = feature_matrix(symbol_frame)
        y = symbol_frame["forward_return_1"].to_numpy(dtype=float)
        x_augmented = np.column_stack([np.ones(len(x)), x])
        params, _, _, _ = np.linalg.lstsq(x_augmented, y, rcond=None)
        return params[1:], float(params[0])

    def _predict(self, symbol: str, features: np.ndarray) -> float:
        return float(self.intercept_by_symbol[symbol] + np.dot(features, self.model_by_symbol[symbol]))


class LogisticRegressionStrategy(_PredictiveModelStrategy):
    name = "logistic_regression"
    prediction_threshold = 0.0

    def _fit_symbol_model(self, symbol: str, symbol_frame: pd.DataFrame) -> tuple[np.ndarray, float]:
        x = feature_matrix(symbol_frame)
        y = (symbol_frame["forward_return_1"] > 0).astype(float).to_numpy()
        mean = x.mean(axis=0)
        std = x.std(axis=0)
        std[std == 0] = 1.0
        x_scaled = (x - mean) / std

        weights = np.zeros(x_scaled.shape[1], dtype=float)
        intercept = 0.0
        learning_rate = 0.1
        regularization = 0.001

        for _ in range(300):
            logits = intercept + x_scaled @ weights
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
            error = probs - y
            intercept -= learning_rate * error.mean()
            weights -= learning_rate * ((x_scaled.T @ error) / len(x_scaled) + regularization * weights)

        self.training_summary.setdefault("normalization", {})[symbol] = {
            "mean": mean.tolist(),
            "std": std.tolist(),
        }
        return weights, intercept

    def _predict(self, symbol: str, features: np.ndarray) -> float:
        normalization = self.training_summary.get("normalization", {}).get(symbol)
        if normalization is None:
            return 0.0
        mean = np.array(normalization["mean"], dtype=float)
        std = np.array(normalization["std"], dtype=float)
        scaled = (features - mean) / std
        logit = float(self.intercept_by_symbol[symbol] + np.dot(scaled, self.model_by_symbol[symbol]))
        probability = 1.0 / (1.0 + np.exp(-np.clip(logit, -30, 30)))
        return probability - 0.5
