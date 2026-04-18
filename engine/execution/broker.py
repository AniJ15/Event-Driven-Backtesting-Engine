from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from queue import Queue

from engine.events import FillEvent, MarketEvent, OrderEvent


@dataclass(slots=True)
class PendingOrder:
    order: OrderEvent
    eligible_at: object
    remaining_quantity: int


class SimulatedBroker:
    """Simple execution simulator with latency, slippage, commissions, and partial fills."""

    def __init__(
        self,
        latency_ms: int = 20,
        slippage_bps: float = 2.0,
        spread_bps: float = 1.0,
        commission_pct: float = 0.0005,
        commission_fixed: float = 1.0,
        max_volume_share: float = 0.1,
    ) -> None:
        self.latency_ms = latency_ms
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps
        self.commission_pct = commission_pct
        self.commission_fixed = commission_fixed
        self.max_volume_share = max_volume_share
        self.pending_orders: list[PendingOrder] = []

    def on_order(self, event: OrderEvent) -> None:
        eligible_at = event.timestamp + timedelta(milliseconds=self.latency_ms)
        self.pending_orders.append(
            PendingOrder(
                order=event,
                eligible_at=eligible_at,
                remaining_quantity=event.quantity,
            )
        )

    def on_market(self, event: MarketEvent, event_queue: Queue) -> None:
        still_pending: list[PendingOrder] = []

        for pending in self.pending_orders:
            if pending.order.symbol != event.symbol:
                still_pending.append(pending)
                continue

            if pending.eligible_at > event.timestamp:
                still_pending.append(pending)
                continue

            if not self._can_fill(pending.order, event.close):
                still_pending.append(pending)
                continue

            fill_qty = self._determine_fill_quantity(pending.remaining_quantity, event.volume)
            fill_price, slippage_cost = self._fill_price(event.close, fill_qty)
            commission = self.commission_fixed + (abs(fill_qty) * fill_price * self.commission_pct)

            event_queue.put(
                FillEvent(
                    timestamp=event.timestamp,
                    symbol=event.symbol,
                    quantity=fill_qty,
                    fill_price=fill_price,
                    commission=commission,
                    slippage_cost=slippage_cost,
                    metadata={
                        "order_type": pending.order.order_type,
                        "limit_price": pending.order.limit_price or 0.0,
                    },
                )
            )

            remainder = pending.remaining_quantity - fill_qty
            if remainder != 0:
                pending.remaining_quantity = remainder
                still_pending.append(pending)

        self.pending_orders = still_pending

    def _can_fill(self, order: OrderEvent, market_price: float) -> bool:
        if order.order_type == "MARKET":
            return True
        if order.limit_price is None:
            return False
        if order.quantity > 0:
            return market_price <= order.limit_price
        return market_price >= order.limit_price

    def _determine_fill_quantity(self, requested_quantity: int, bar_volume: float) -> int:
        max_fill = max(1, int(bar_volume * self.max_volume_share))
        fill_size = min(abs(requested_quantity), max_fill)
        return fill_size if requested_quantity > 0 else -fill_size

    def _fill_price(self, market_price: float, quantity: int) -> tuple[float, float]:
        direction = 1 if quantity > 0 else -1
        impact_bps = self.slippage_bps + (self.spread_bps / 2.0)
        fill_price = market_price * (1 + (direction * impact_bps / 10_000))
        slippage_cost = abs(quantity) * abs(fill_price - market_price)
        return fill_price, slippage_cost
