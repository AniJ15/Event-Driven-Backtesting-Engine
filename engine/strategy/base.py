from __future__ import annotations

from queue import Queue

from engine.events import MarketEvent


class Strategy:
    """Base strategy interface."""

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        raise NotImplementedError
