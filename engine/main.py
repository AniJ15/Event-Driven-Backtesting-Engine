from __future__ import annotations

import argparse
from pathlib import Path
from queue import Queue

import pandas as pd

from engine.analytics.metrics import compute_metrics, compute_symbol_metrics
from engine.data.data_handler import MultiAssetCSVDataHandler
from engine.events import FillEvent, MarketEvent, OrderEvent, SignalEvent
from engine.execution.broker import SimulatedBroker
from engine.portfolio.portfolio import Portfolio
from engine.reporting import build_suite_payload, write_report_json
from engine.risk.engine import RiskEngine
from engine.strategy.router import SUPPORTED_STRATEGIES, create_strategy


def run_backtest(
    market_data: pd.DataFrame,
    strategy_name: str,
    initial_cash: float,
    order_size: int,
    training_data: pd.DataFrame | None = None,
) -> dict[str, object]:
    event_queue: Queue = Queue()
    symbols = sorted(market_data["symbol"].unique())
    data_handler = MultiAssetCSVDataHandler(data_frame=market_data)
    portfolio = Portfolio(
        initial_cash=initial_cash,
        base_order_size=order_size,
        order_size_by_symbol={symbol: order_size for symbol in symbols},
    )
    broker = SimulatedBroker()
    strategy = create_strategy(strategy_name=strategy_name, symbols=symbols)
    training_summary = strategy.fit(training_data if training_data is not None else market_data)
    risk_engine = RiskEngine(initial_equity=initial_cash)

    for timestamp, market_events in data_handler.stream_market_event_batches():
        for market_event in market_events:
            event_queue.put(market_event)

        while not event_queue.empty():
            event = event_queue.get()

            if isinstance(event, MarketEvent):
                broker.on_market(event, event_queue)
                portfolio.on_market(event)
                risk_engine.on_market(event, portfolio, event_queue)
                strategy.on_market(event, event_queue)
            elif isinstance(event, SignalEvent):
                approved_signal = risk_engine.on_signal(event, portfolio)
                if approved_signal is not None:
                    portfolio.on_signal(approved_signal, event_queue)
            elif isinstance(event, OrderEvent):
                broker.on_order(event)
            elif isinstance(event, FillEvent):
                portfolio.on_fill(event)
                risk_engine.on_fill(event, portfolio)

        portfolio.record_snapshot(timestamp)

    equity_frame = portfolio.get_equity_frame()
    fills_frame = portfolio.get_fills_frame()
    symbol_summary = portfolio.get_symbol_summary_frame()
    symbol_metrics = compute_symbol_metrics(market_data, fills_frame, symbol_summary)
    risk_log = pd.DataFrame(risk_engine.get_risk_log())
    metrics = {
        **portfolio.summary(),
        **compute_metrics(equity_frame, total_trade_notional=portfolio.trade_notional),
        "symbol_count": len(symbols),
        "risk_events": int(len(risk_log)),
    }

    return {
        "strategy_name": strategy_name,
        "metrics": metrics,
        "equity_frame": equity_frame,
        "fills_frame": fills_frame,
        "symbol_summary": symbol_summary,
        "symbol_metrics": symbol_metrics,
        "market_data": market_data,
        "risk_log": risk_log,
        "training_summary": training_summary,
    }


def run_strategy_suite(
    data_sources: dict[str, str | Path],
    strategy_names: list[str],
    initial_cash: float,
    order_size: int,
    train_ratio: float,
) -> dict[str, object]:
    full_data = MultiAssetCSVDataHandler(csv_paths_by_symbol=data_sources).get_data_frame()
    training_data, testing_data, split_info = split_train_test(full_data, train_ratio)

    experiments: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    for strategy_name in strategy_names:
        result = run_backtest(
            market_data=testing_data,
            strategy_name=strategy_name,
            initial_cash=initial_cash,
            order_size=order_size,
            training_data=training_data,
        )
        experiments.append(result)
        comparison_rows.append(
            {
                "strategy": strategy_name,
                **result["metrics"],
            }
        )

    comparison_frame = pd.DataFrame(comparison_rows).sort_values(
        by="cumulative_return", ascending=False
    ).reset_index(drop=True)
    return {
        "training_data": training_data,
        "testing_data": testing_data,
        "split_info": split_info,
        "experiments": experiments,
        "comparison_frame": comparison_frame,
        "strategy_names": strategy_names,
    }


def split_train_test(data: pd.DataFrame, train_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if not 0.5 <= train_ratio < 0.95:
        raise ValueError("train_ratio must be between 0.5 and 0.95")

    ordered_timestamps = sorted(pd.to_datetime(data["timestamp"]).unique())
    split_index = max(1, int(len(ordered_timestamps) * train_ratio))
    split_index = min(split_index, len(ordered_timestamps) - 1)
    split_timestamp = ordered_timestamps[split_index]

    training_data = data.loc[data["timestamp"] < split_timestamp].copy().reset_index(drop=True)
    testing_data = data.loc[data["timestamp"] >= split_timestamp].copy().reset_index(drop=True)
    split_info = {
        "train_ratio": train_ratio,
        "train_start": str(training_data["timestamp"].min()),
        "train_end": str(training_data["timestamp"].max()),
        "test_start": str(testing_data["timestamp"].min()),
        "test_end": str(testing_data["timestamp"].max()),
        "train_rows": int(len(training_data)),
        "test_rows": int(len(testing_data)),
    }
    return training_data, testing_data, split_info


def execute_backtest(
    data_sources: dict[str, str | Path],
    strategy_names: list[str],
    initial_cash: float,
    order_size: int,
    train_ratio: float,
    report_json: str | Path,
) -> dict[str, object]:
    suite = run_strategy_suite(
        data_sources=data_sources,
        strategy_names=strategy_names,
        initial_cash=initial_cash,
        order_size=order_size,
        train_ratio=train_ratio,
    )
    payload_path = write_report_json(
        output_path=report_json,
        suite=suite,
        config={
            "initial_cash": initial_cash,
            "order_size": order_size,
            "train_ratio": train_ratio,
            "data_sources": {symbol: str(path) for symbol, path in data_sources.items()},
            "strategy_names": strategy_names,
        },
    )
    return {
        **suite,
        "json_path": payload_path,
        "payload": build_suite_payload(
            suite=suite,
            config={
                "initial_cash": initial_cash,
                "order_size": order_size,
                "train_ratio": train_ratio,
                "data_sources": {symbol: str(path) for symbol, path in data_sources.items()},
                "strategy_names": strategy_names,
            },
        ),
    }


def _parse_csv_mappings(csv_mappings: list[str] | None) -> dict[str, str]:
    sources: dict[str, str] = {}
    if not csv_mappings:
        return sources
    for mapping in csv_mappings:
        if "=" not in mapping:
            raise ValueError(f"Invalid --csv value '{mapping}'. Use SYMBOL=path/to/file.csv")
        symbol, path = mapping.split("=", 1)
        symbol = symbol.strip().upper()
        path = path.strip()
        if not symbol or not path:
            raise ValueError(f"Invalid --csv value '{mapping}'. Use SYMBOL=path/to/file.csv")
        sources[symbol] = path
    return sources


def _discover_data_sources(data_dir: str | None, symbols: list[str] | None) -> dict[str, str]:
    if data_dir is None:
        return {}
    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"Data directory does not exist: {root}")
    requested_symbols = None if not symbols else {symbol.upper() for symbol in symbols}
    sources: dict[str, str] = {}
    for csv_path in sorted(root.glob("*.csv")):
        symbol = csv_path.stem.upper()
        if requested_symbols is not None and symbol not in requested_symbols:
            continue
        sources[symbol] = str(csv_path)
    return sources


def _parse_strategy_names(strategy_names_arg: str | None) -> list[str]:
    if not strategy_names_arg:
        return ["moving_average", "mean_reversion", "linear_regression", "logistic_regression"]
    names = [item.strip().lower() for item in strategy_names_arg.split(",") if item.strip()]
    invalid = [name for name in names if name not in SUPPORTED_STRATEGIES]
    if invalid:
        available = ", ".join(sorted(SUPPORTED_STRATEGIES))
        raise ValueError(f"Unsupported strategy names {invalid}. Available: {available}")
    return names


def build_run_configuration(
    csv_mappings: list[str] | None,
    data_dir: str | None,
    symbols_arg: str | None,
    strategies_arg: str | None,
    initial_cash: float,
    order_size: int,
    train_ratio: float,
    report_json: str | Path,
) -> dict[str, object]:
    symbols = None if not symbols_arg else [
        symbol.strip().upper() for symbol in symbols_arg.split(",") if symbol.strip()
    ]
    data_sources = _parse_csv_mappings(csv_mappings)
    if not data_sources:
        data_sources = _discover_data_sources(data_dir, symbols)
    elif symbols:
        requested = set(symbols)
        data_sources = {symbol: path for symbol, path in data_sources.items() if symbol in requested}
    if not data_sources:
        raise ValueError("No data sources found. Provide --csv mappings or a populated --data-dir.")

    strategy_names = _parse_strategy_names(strategies_arg)
    return {
        "data_sources": data_sources,
        "strategy_names": strategy_names,
        "initial_cash": initial_cash,
        "order_size": order_size,
        "train_ratio": train_ratio,
        "report_json": report_json,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the strategy comparison backtest suite.")
    parser.add_argument("--csv", action="append", help="Explicit mapping SYMBOL=path/to/file.csv")
    parser.add_argument("--data-dir", default="sample_data", help="Directory of per-symbol CSV files")
    parser.add_argument("--symbols", help="Comma-separated subset of symbols to trade")
    parser.add_argument(
        "--strategies",
        help="Comma-separated strategies to compare. Default compares all built-in strategies.",
    )
    parser.add_argument("--initial-cash", type=float, default=100_000.0, help="Starting cash")
    parser.add_argument("--order-size", type=int, default=100, help="Per-symbol target position size")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="Fraction of data used for training")
    parser.add_argument(
        "--report-json",
        default="artifacts/backtest_results.json",
        help="Path to the generated JSON report artifact",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = build_run_configuration(
        csv_mappings=args.csv,
        data_dir=args.data_dir,
        symbols_arg=args.symbols,
        strategies_arg=args.strategies,
        initial_cash=args.initial_cash,
        order_size=args.order_size,
        train_ratio=args.train_ratio,
        report_json=args.report_json,
    )
    results = execute_backtest(**config)

    print("Train/Test Split")
    for key, value in results["split_info"].items():
        print(f"  {key}: {value}")

    print("\nStrategy Comparison")
    print(results["comparison_frame"].to_string(index=False))
    print(f"\nReport JSON written to {results['json_path']}")


if __name__ == "__main__":
    main()
