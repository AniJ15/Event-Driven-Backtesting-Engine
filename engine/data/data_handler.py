from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

from engine.events import MarketEvent


class CSVDataHandler:
    """Streams market data from a CSV file as MarketEvents."""

    def __init__(self, csv_path: str | Path, symbol: str) -> None:
        self.csv_path = Path(csv_path)
        self.symbol = symbol
        self._data = self._load_data()
        self._latest_bar: pd.Series | None = None

    def _load_data(self) -> pd.DataFrame:
        data = pd.read_csv(self.csv_path, parse_dates=["timestamp"])
        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required_columns.difference(data.columns)
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"CSV is missing required columns: {missing_str}")

        data = data.sort_values("timestamp").reset_index(drop=True)
        return data

    def stream_market_events(self) -> Iterator[MarketEvent]:
        for _, row in self._data.iterrows():
            self._latest_bar = row
            yield MarketEvent(
                timestamp=row["timestamp"].to_pydatetime(),
                symbol=self.symbol,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )

    def get_latest_close(self) -> float | None:
        if self._latest_bar is None:
            return None
        return float(self._latest_bar["close"])

    def get_data_frame(self) -> pd.DataFrame:
        return self._data.copy()
