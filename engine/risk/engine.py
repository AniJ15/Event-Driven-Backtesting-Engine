from __future__ import annotations

from engine.events import FillEvent, MarketEvent, SignalEvent


class RiskEngine:
    """Applies portfolio- and position-level risk controls."""

    def __init__(
        self,
        initial_equity: float,
        max_symbol_exposure: float = 0.35,
        max_gross_leverage: float = 1.2,
        stop_loss_pct: float = 0.08,
        max_drawdown_pct: float = 0.15,
    ) -> None:
        self.max_symbol_exposure = max_symbol_exposure
        self.max_gross_leverage = max_gross_leverage
        self.stop_loss_pct = stop_loss_pct
        self.max_drawdown_pct = max_drawdown_pct

        self.peak_equity = initial_equity
        self.drawdown_breached = False
        self.active_protective_exits: set[str] = set()
        self.risk_actions: list[dict[str, object]] = []

    def on_market(self, event: MarketEvent, portfolio: object, event_queue: object) -> None:
        equity = portfolio.total_equity()
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 0.0 if self.peak_equity == 0 else (equity / self.peak_equity) - 1.0

        if not self.drawdown_breached and drawdown <= -self.max_drawdown_pct:
            self.drawdown_breached = True
            self._record_action(
                timestamp=event.timestamp,
                symbol="PORTFOLIO",
                action="DRAWDOWN_EXIT",
                detail=(
                    f"Drawdown {drawdown:.4f} breached max drawdown "
                    f"{-self.max_drawdown_pct:.4f}; forcing portfolio de-risk."
                ),
            )
            for symbol, quantity in portfolio.positions.items():
                if quantity != 0:
                    self._emit_exit(event.timestamp, symbol, event_queue, "MAX_DRAWDOWN")

        quantity = portfolio.positions.get(event.symbol, 0)
        if quantity == 0:
            self.active_protective_exits.discard(event.symbol)
            return

        average_cost = portfolio.average_cost.get(event.symbol, 0.0)
        if average_cost <= 0 or event.symbol in self.active_protective_exits:
            return

        stop_triggered = (
            quantity > 0 and event.close <= average_cost * (1.0 - self.stop_loss_pct)
        ) or (
            quantity < 0 and event.close >= average_cost * (1.0 + self.stop_loss_pct)
        )
        if stop_triggered:
            self._record_action(
                timestamp=event.timestamp,
                symbol=event.symbol,
                action="STOP_LOSS_EXIT",
                detail=(
                    f"Price {event.close:.2f} breached stop-loss against avg cost "
                    f"{average_cost:.2f}."
                ),
            )
            self._emit_exit(event.timestamp, event.symbol, event_queue, "STOP_LOSS")

    def on_signal(self, event: SignalEvent, portfolio: object) -> SignalEvent | None:
        if event.metadata.get("risk_approved") == "1":
            return event

        if event.symbol in self.active_protective_exits and event.direction != "EXIT":
            self._record_action(
                timestamp=event.timestamp,
                symbol=event.symbol,
                action="SIGNAL_BLOCKED",
                detail="New signal blocked while a protective exit is still active.",
            )
            return None

        current_position = portfolio.positions.get(event.symbol, 0)
        desired_target = portfolio.resolve_target_position(event.symbol, event)
        price = portfolio.latest_prices.get(event.symbol)
        equity = portfolio.total_equity()

        if event.direction != "EXIT" and self.drawdown_breached:
            self._record_action(
                timestamp=event.timestamp,
                symbol=event.symbol,
                action="SIGNAL_BLOCKED",
                detail="New directional exposure blocked after drawdown breach.",
            )
            return None

        if event.direction == "EXIT":
            approved_target = 0
        else:
            if price is None or price <= 0 or equity <= 0:
                self._record_action(
                    timestamp=event.timestamp,
                    symbol=event.symbol,
                    action="SIGNAL_BLOCKED",
                    detail="Signal blocked because price/equity context was unavailable.",
                )
                return None

            approved_target = self._cap_target_by_symbol_exposure(
                target_quantity=desired_target,
                price=price,
                equity=equity,
            )
            approved_target = self._cap_target_by_gross_leverage(
                symbol=event.symbol,
                target_quantity=approved_target,
                portfolio=portfolio,
                price=price,
                equity=equity,
            )

        if approved_target == current_position:
            self._record_action(
                timestamp=event.timestamp,
                symbol=event.symbol,
                action="SIGNAL_BLOCKED",
                detail="Risk checks reduced the target to the current position.",
            )
            return None

        if approved_target != desired_target:
            self._record_action(
                timestamp=event.timestamp,
                symbol=event.symbol,
                action="SIGNAL_RESIZED",
                detail=(
                    f"Target resized from {desired_target} to {approved_target} "
                    "to respect risk limits."
                ),
            )

        approved_metadata = dict(event.metadata)
        approved_metadata["target_quantity"] = str(approved_target)
        approved_metadata["risk_approved"] = "1"

        direction = event.direction
        if approved_target == 0:
            direction = "EXIT"
        elif approved_target > 0:
            direction = "LONG"
        elif approved_target < 0:
            direction = "SHORT"

        return SignalEvent(
            timestamp=event.timestamp,
            symbol=event.symbol,
            direction=direction,
            strength=event.strength,
            metadata=approved_metadata,
        )

    def on_fill(self, event: FillEvent, portfolio: object) -> None:
        if portfolio.positions.get(event.symbol, 0) == 0:
            self.active_protective_exits.discard(event.symbol)

    def get_risk_log(self) -> list[dict[str, object]]:
        return list(self.risk_actions)

    def _emit_exit(self, timestamp: object, symbol: str, event_queue: object, reason: str) -> None:
        self.active_protective_exits.add(symbol)
        event_queue.put(
            SignalEvent(
                timestamp=timestamp,
                symbol=symbol,
                direction="EXIT",
                metadata={
                    "reason": reason,
                    "target_quantity": "0",
                    "risk_approved": "1",
                },
            )
        )

    def _cap_target_by_symbol_exposure(
        self,
        target_quantity: int,
        price: float,
        equity: float,
    ) -> int:
        max_notional = equity * self.max_symbol_exposure
        max_quantity = int(max_notional / price)
        if max_quantity <= 0:
            return 0
        if target_quantity > 0:
            return min(target_quantity, max_quantity)
        if target_quantity < 0:
            return max(target_quantity, -max_quantity)
        return 0

    def _cap_target_by_gross_leverage(
        self,
        symbol: str,
        target_quantity: int,
        portfolio: object,
        price: float,
        equity: float,
    ) -> int:
        allowed_gross = equity * self.max_gross_leverage
        gross_other_positions = 0.0
        for existing_symbol, quantity in portfolio.positions.items():
            if existing_symbol == symbol:
                continue
            latest_price = portfolio.latest_prices.get(existing_symbol, 0.0)
            gross_other_positions += abs(quantity) * latest_price

        remaining_room = max(0.0, allowed_gross - gross_other_positions)
        max_quantity = int(remaining_room / price)
        if max_quantity <= 0:
            return 0
        if target_quantity > 0:
            return min(target_quantity, max_quantity)
        if target_quantity < 0:
            return max(target_quantity, -max_quantity)
        return 0

    def _record_action(self, timestamp: object, symbol: str, action: str, detail: str) -> None:
        self.risk_actions.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "action": action,
                "detail": detail,
            }
        )
