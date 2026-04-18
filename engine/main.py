from __future__ import annotations

import argparse
from queue import Queue

import pandas as pd

from engine.analytics.metrics import compute_metrics
from engine.data.data_handler import CSVDataHandler
from engine.events import FillEvent, MarketEvent, OrderEvent, SignalEvent
from engine.execution.broker import SimulatedBroker
from engine.portfolio.portfolio import Portfolio
from engine.strategy.moving_average import MovingAverageCrossStrategy


def run_backtest(
    csv_path: str,
    symbol: str,
    initial_cash: float,
    order_size: int,
) -> tuple[dict[str, float], pd.DataFrame, pd.DataFrame]:
    event_queue: Queue = Queue()
    data_handler = CSVDataHandler(csv_path=csv_path, symbol=symbol)
    strategy = MovingAverageCrossStrategy(symbol=symbol)
    portfolio = Portfolio(initial_cash=initial_cash, base_order_size=order_size)
    broker = SimulatedBroker()

    for market_event in data_handler.stream_market_events():
        event_queue.put(market_event)

        while not event_queue.empty():
            event = event_queue.get()

            if isinstance(event, MarketEvent):
                broker.on_market(event, event_queue)
                portfolio.on_market(event)
                strategy.on_market(event, event_queue)
            elif isinstance(event, SignalEvent):
                portfolio.on_signal(event, event_queue)
            elif isinstance(event, OrderEvent):
                broker.on_order(event)
            elif isinstance(event, FillEvent):
                portfolio.on_fill(event)

        portfolio.record_snapshot(market_event.timestamp)

    equity_frame = portfolio.get_equity_frame()
    fills_frame = portfolio.get_fills_frame()
    metrics = {
        **portfolio.summary(),
        **compute_metrics(equity_frame, total_trade_notional=portfolio.trade_notional),
    }
    return metrics, equity_frame, fills_frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the event-driven backtest.")
    parser.add_argument("--csv", default="sample_data/AAPL.csv", help="Path to OHLCV CSV data")
    parser.add_argument("--symbol", default="AAPL", help="Symbol for the CSV data")
    parser.add_argument("--initial-cash", type=float, default=100_000.0, help="Starting cash")
    parser.add_argument("--order-size", type=int, default=100, help="Target position size")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics, equity_frame, fills_frame = run_backtest(
        csv_path=args.csv,
        symbol=args.symbol,
        initial_cash=args.initial_cash,
        order_size=args.order_size,
    )

    print("Performance Summary")
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    if not fills_frame.empty:
        print("\nRecent fills")
        print(fills_frame.tail(5).to_string(index=False))

    if not equity_frame.empty:
        print("\nEquity curve tail")
        print(equity_frame.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
