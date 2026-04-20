from __future__ import annotations

import pandas as pd
from queue import Queue

from engine.events import MarketEvent


class Strategy:
    """Base strategy interface."""

    name = "base"

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = set(symbols)
        self.training_summary: dict[str, object] = {}

    def fit(self, training_data: pd.DataFrame) -> dict[str, object]:
        self.training_summary = {}
        return self.training_summary

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        raise NotImplementedError
