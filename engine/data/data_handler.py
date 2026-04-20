from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

from engine.events import MarketEvent


class MultiAssetCSVDataHandler:
    """Streams multiple CSV files into a single chronological market event feed."""

    def __init__(
        self,
        csv_paths_by_symbol: dict[str, str | Path] | None = None,
        data_frame: pd.DataFrame | None = None,
    ) -> None:
        if data_frame is None and not csv_paths_by_symbol:
            raise ValueError("At least one symbol/data source must be provided")

        self.csv_paths_by_symbol = (
            {symbol: Path(csv_path) for symbol, csv_path in csv_paths_by_symbol.items()}
            if csv_paths_by_symbol
            else {}
        )
        self._data = self._normalize_frame(data_frame.copy()) if data_frame is not None else self._load_data()
        self._latest_bars: dict[str, pd.Series] = {}

    def _load_data(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}

        for symbol, csv_path in self.csv_paths_by_symbol.items():
            data = pd.read_csv(csv_path, parse_dates=["timestamp"])
            missing = required_columns.difference(data.columns)
            if missing:
                missing_str = ", ".join(sorted(missing))
                raise ValueError(f"{csv_path} is missing required columns: {missing_str}")

            frame = data.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
            frame["symbol"] = symbol
            frames.append(frame)

        combined = pd.concat(frames, ignore_index=True)
        return self._normalize_frame(combined)

    @staticmethod
    def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
        expected = {"timestamp", "open", "high", "low", "close", "volume", "symbol"}
        missing = expected.difference(frame.columns)
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"Data frame is missing required columns: {missing_str}")
        normalized = frame.copy()
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"])
        normalized = normalized.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
        return normalized

    def stream_market_event_batches(self) -> Iterator[tuple[object, list[MarketEvent]]]:
        for timestamp, batch in self._data.groupby("timestamp", sort=True):
            events: list[MarketEvent] = []
            for _, row in batch.iterrows():
                self._latest_bars[row["symbol"]] = row
                events.append(
                    MarketEvent(
                        timestamp=row["timestamp"].to_pydatetime(),
                        symbol=row["symbol"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
            yield timestamp.to_pydatetime(), events

    def get_latest_close(self, symbol: str) -> float | None:
        latest_bar = self._latest_bars.get(symbol)
        if latest_bar is None:
            return None
        return float(latest_bar["close"])

    def get_data_frame(self) -> pd.DataFrame:
        return self._data.copy()
