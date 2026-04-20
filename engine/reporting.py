from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_report_json(
    output_path: str | Path,
    suite: dict[str, object],
    config: dict[str, object],
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_suite_payload(suite=suite, config=config)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def build_suite_payload(
    suite: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    experiments_payload: list[dict[str, object]] = []
    for experiment in suite["experiments"]:
        experiments_payload.append(
            {
                "strategy_name": experiment["strategy_name"],
                "metrics": experiment["metrics"],
                "training_summary": experiment["training_summary"],
                "equity_curve": _frame_to_records(experiment["equity_frame"]),
                "fills": _frame_to_records(experiment["fills_frame"]),
                "symbol_summary": _frame_to_records(experiment["symbol_summary"]),
                "symbol_metrics": _frame_to_records(experiment["symbol_metrics"]),
                "market_data": _frame_to_records(experiment["market_data"]),
                "risk_log": _frame_to_records(experiment["risk_log"]),
            }
        )

    return {
        "config": config,
        "split_info": suite["split_info"],
        "comparison": _frame_to_records(suite["comparison_frame"]),
        "training_data": _frame_to_records(suite["training_data"]),
        "testing_data": _frame_to_records(suite["testing_data"]),
        "experiments": experiments_payload,
    }


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []

    serializable = frame.copy()
    for column in serializable.columns:
        if pd.api.types.is_datetime64_any_dtype(serializable[column]):
            serializable[column] = serializable[column].astype(str)
        else:
            serializable[column] = serializable[column].map(_normalize_value)
    return serializable.to_dict(orient="records")


def _normalize_value(value: object) -> object:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if isinstance(value, float):
        return round(value, 6)
    return value
