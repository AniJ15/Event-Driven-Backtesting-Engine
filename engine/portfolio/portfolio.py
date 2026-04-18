from __future__ import annotations

from dataclasses import asdict
from queue import Queue

import pandas as pd

from engine.events import FillEvent, MarketEvent, OrderEvent, SignalEvent


class Portfolio:
    """Tracks positions, cash, and equity over time."""

    def __init__(self, initial_cash: float = 100_000.0, base_order_size: int = 100) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.base_order_size = base_order_size

        self.positions: dict[str, int] = {}
        self.average_cost: dict[str, float] = {}
        self.latest_prices: dict[str, float] = {}

        self.realized_pnl = 0.0
        self.total_commission = 0.0
        self.total_slippage = 0.0
        self.trade_notional = 0.0

        self.fills: list[dict[str, object]] = []
        self.equity_curve: list[dict[str, float | object]] = []

    def on_market(self, event: MarketEvent) -> None:
        self.latest_prices[event.symbol] = event.close

    def record_snapshot(self, timestamp: object) -> None:
        self._record_equity_snapshot(timestamp)

    def on_signal(self, event: SignalEvent, event_queue: Queue) -> None:
        current_position = self.positions.get(event.symbol, 0)
        target_position = self._target_position_for_signal(event.direction)
        order_quantity = target_position - current_position

        if order_quantity == 0:
            return

        event_queue.put(
            OrderEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                quantity=order_quantity,
                order_type="MARKET",
            )
        )

    def on_fill(self, event: FillEvent) -> None:
        symbol = event.symbol
        fill_qty = event.quantity
        fill_price = event.fill_price
        previous_position = self.positions.get(symbol, 0)
        average_cost = self.average_cost.get(symbol, 0.0)

        realized_change, next_position, next_average_cost = self._book_fill(
            previous_position=previous_position,
            average_cost=average_cost,
            fill_qty=fill_qty,
            fill_price=fill_price,
        )

        self.positions[symbol] = next_position
        self.average_cost[symbol] = next_average_cost if next_position != 0 else 0.0
        self.realized_pnl += realized_change
        self.total_commission += event.commission
        self.total_slippage += event.slippage_cost
        self.trade_notional += abs(fill_qty * fill_price)

        self.cash -= (fill_qty * fill_price) + event.commission
        self.fills.append(asdict(event))

    def holdings_value(self) -> float:
        return sum(
            quantity * self.latest_prices.get(symbol, 0.0)
            for symbol, quantity in self.positions.items()
        )

    def total_equity(self) -> float:
        return self.cash + self.holdings_value()

    def unrealized_pnl(self) -> float:
        total = 0.0
        for symbol, quantity in self.positions.items():
            if quantity == 0:
                continue
            price = self.latest_prices.get(symbol)
            if price is None:
                continue
            total += (price - self.average_cost.get(symbol, 0.0)) * quantity
        return total

    def leverage(self) -> float:
        equity = self.total_equity()
        if equity == 0:
            return 0.0
        gross_exposure = sum(
            abs(quantity) * self.latest_prices.get(symbol, 0.0)
            for symbol, quantity in self.positions.items()
        )
        return gross_exposure / equity

    def get_equity_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.equity_curve)

    def get_fills_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.fills)

    def summary(self) -> dict[str, float]:
        return {
            "cash": round(self.cash, 2),
            "holdings_value": round(self.holdings_value(), 2),
            "total_equity": round(self.total_equity(), 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl(), 2),
            "total_commission": round(self.total_commission, 2),
            "total_slippage": round(self.total_slippage, 2),
            "leverage": round(self.leverage(), 4),
        }

    def _target_position_for_signal(self, direction: str) -> int:
        if direction == "LONG":
            return self.base_order_size
        if direction == "SHORT":
            return -self.base_order_size
        return 0

    def _record_equity_snapshot(self, timestamp: object) -> None:
        self.equity_curve.append(
            {
                "timestamp": timestamp,
                "cash": self.cash,
                "holdings_value": self.holdings_value(),
                "total_equity": self.total_equity(),
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": self.unrealized_pnl(),
                "leverage": self.leverage(),
            }
        )

    @staticmethod
    def _book_fill(
        previous_position: int,
        average_cost: float,
        fill_qty: int,
        fill_price: float,
    ) -> tuple[float, int, float]:
        if previous_position == 0:
            return 0.0, fill_qty, fill_price

        if previous_position > 0 and fill_qty > 0:
            new_position = previous_position + fill_qty
            new_average = (
                (previous_position * average_cost) + (fill_qty * fill_price)
            ) / new_position
            return 0.0, new_position, new_average

        if previous_position < 0 and fill_qty < 0:
            new_position = previous_position + fill_qty
            new_average = (
                (abs(previous_position) * average_cost) + (abs(fill_qty) * fill_price)
            ) / abs(new_position)
            return 0.0, new_position, new_average

        closing_qty = min(abs(previous_position), abs(fill_qty))
        realized = 0.0

        if previous_position > 0:
            realized += (fill_price - average_cost) * closing_qty
        else:
            realized += (average_cost - fill_price) * closing_qty

        next_position = previous_position + fill_qty
        if next_position == 0:
            return realized, 0, 0.0

        if (previous_position > 0 and next_position > 0) or (
            previous_position < 0 and next_position < 0
        ):
            return realized, next_position, average_cost

        return realized, next_position, fill_price
