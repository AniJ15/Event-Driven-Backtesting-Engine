from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass(slots=True)
class Event:
    """Base event type."""

    timestamp: datetime


@dataclass(slots=True)
class MarketEvent(Event):
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class SignalEvent(Event):
    symbol: str
    direction: Literal["LONG", "SHORT", "EXIT"]
    strength: float = 1.0
    metadata: dict[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class OrderEvent(Event):
    symbol: str
    quantity: int
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: Optional[float] = None

    @property
    def direction(self) -> Literal["BUY", "SELL"]:
        return "BUY" if self.quantity > 0 else "SELL"


@dataclass(slots=True)
class FillEvent(Event):
    symbol: str
    quantity: int
    fill_price: float
    commission: float
    slippage_cost: float
    metadata: dict[str, float | str] = field(default_factory=dict)
