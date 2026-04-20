from __future__ import annotations

from collections import deque
from math import sqrt
from queue import Queue

import pandas as pd

from engine.events import MarketEvent, SignalEvent
from engine.strategy.base import Strategy


class MeanReversionStrategy(Strategy):
    """Simple z-score mean reversion strategy."""

    name = "mean_reversion"

    def __init__(
        self,
        symbols: list[str],
        lookback: int = 15,
        entry_zscore: float = 1.2,
        exit_zscore: float = 0.35,
    ) -> None:
        super().__init__(symbols)
        self.lookback = lookback
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.prices: dict[str, deque[float]] = {
            symbol: deque(maxlen=lookback) for symbol in symbols
        }
        self.current_regime: dict[str, str] = {symbol: "FLAT" for symbol in symbols}

    def fit(self, training_data: pd.DataFrame) -> dict[str, object]:
        for symbol in self.symbols:
            symbol_data = training_data.loc[training_data["symbol"] == symbol, "close"].tail(self.lookback)
            self.prices[symbol].clear()
            self.prices[symbol].extend(float(value) for value in symbol_data)
            self.current_regime[symbol] = "FLAT"
        self.training_summary = {
            "strategy": self.name,
            "lookback": self.lookback,
            "entry_zscore": self.entry_zscore,
            "exit_zscore": self.exit_zscore,
        }
        return self.training_summary

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        if event.symbol not in self.symbols:
            return

        history = self.prices[event.symbol]
        history.append(event.close)
        if len(history) < self.lookback:
            return

        prices = list(history)
        mean_price = sum(prices) / len(prices)
        variance = sum((price - mean_price) ** 2 for price in prices) / len(prices)
        std_dev = sqrt(variance)
        if std_dev == 0:
            return

        zscore = (event.close - mean_price) / std_dev
        current_regime = self.current_regime[event.symbol]
        next_regime = current_regime

        if zscore >= self.entry_zscore:
            next_regime = "SHORT"
        elif zscore <= -self.entry_zscore:
            next_regime = "LONG"
        elif abs(zscore) <= self.exit_zscore:
            next_regime = "EXIT"

        if next_regime == current_regime or (current_regime == "FLAT" and next_regime == "EXIT"):
            return

        self.current_regime[event.symbol] = "FLAT" if next_regime == "EXIT" else next_regime
        event_queue.put(
            SignalEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                direction=next_regime,
                strength=min(2.0, abs(zscore)),
                metadata={
                    "strategy": self.name,
                    "zscore": f"{zscore:.4f}",
                    "mean_price": f"{mean_price:.4f}",
                },
            )
        )
