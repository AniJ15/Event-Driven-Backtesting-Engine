from __future__ import annotations

from collections import deque
from queue import Queue

from engine.events import MarketEvent, SignalEvent
from engine.strategy.base import Strategy


class MovingAverageCrossStrategy(Strategy):
    """Simple trend-following strategy using two moving averages."""

    def __init__(self, symbol: str, short_window: int = 5, long_window: int = 12) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")

        self.symbol = symbol
        self.short_window = short_window
        self.long_window = long_window
        self.prices: deque[float] = deque(maxlen=long_window)
        self.current_regime: str = "FLAT"

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        if event.symbol != self.symbol:
            return

        self.prices.append(event.close)
        if len(self.prices) < self.long_window:
            return

        prices = list(self.prices)
        short_ma = sum(prices[-self.short_window :]) / self.short_window
        long_ma = sum(prices) / self.long_window

        next_regime = "LONG" if short_ma > long_ma else "SHORT"
        if next_regime == self.current_regime:
            return

        self.current_regime = next_regime
        event_queue.put(
            SignalEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                direction=next_regime,
                strength=1.0,
                metadata={
                    "short_ma": round(short_ma, 4),
                    "long_ma": round(long_ma, 4),
                },
            )
        )
