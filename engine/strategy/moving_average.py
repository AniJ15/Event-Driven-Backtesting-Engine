from __future__ import annotations

from collections import deque
from queue import Queue

import pandas as pd

from engine.events import MarketEvent, SignalEvent
from engine.strategy.base import Strategy


class MovingAverageCrossStrategy(Strategy):
    """Simple trend-following strategy using two moving averages per symbol."""

    name = "moving_average"

    def __init__(
        self,
        symbols: list[str],
        short_window: int = 5,
        long_window: int = 12,
    ) -> None:
        super().__init__(symbols)
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")

        self.short_window = short_window
        self.long_window = long_window
        self.prices: dict[str, deque[float]] = {
            symbol: deque(maxlen=long_window) for symbol in symbols
        }
        self.current_regime: dict[str, str] = {symbol: "FLAT" for symbol in symbols}

    def fit(self, training_data: pd.DataFrame) -> dict[str, object]:
        for symbol in self.symbols:
            symbol_data = training_data.loc[training_data["symbol"] == symbol, "close"].tail(self.long_window)
            self.prices[symbol].clear()
            self.prices[symbol].extend(float(value) for value in symbol_data)
            self.current_regime[symbol] = "FLAT"
        self.training_summary = {
            "strategy": self.name,
            "short_window": self.short_window,
            "long_window": self.long_window,
        }
        return self.training_summary

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        if event.symbol not in self.symbols:
            return

        symbol_prices = self.prices[event.symbol]
        symbol_prices.append(event.close)
        if len(symbol_prices) < self.long_window:
            return

        prices = list(symbol_prices)
        short_ma = sum(prices[-self.short_window :]) / self.short_window
        long_ma = sum(prices) / self.long_window

        next_regime = "LONG" if short_ma > long_ma else "SHORT"
        if next_regime == self.current_regime[event.symbol]:
            return

        self.current_regime[event.symbol] = next_regime
        event_queue.put(
            SignalEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                direction=next_regime,
                strength=1.0,
                metadata={
                    "strategy": self.name,
                    "short_ma": round(short_ma, 4),
                    "long_ma": round(long_ma, 4),
                },
            )
        )
