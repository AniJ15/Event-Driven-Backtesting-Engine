from __future__ import annotations

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "ret_1",
    "ret_3",
    "ret_5",
    "momentum_10",
    "momentum_20",
    "volatility_10",
    "volume_z_10",
]


def build_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.sort_values(["symbol", "timestamp"]).copy()
    grouped = frame.groupby("symbol", group_keys=False)

    frame["ret_1"] = grouped["close"].pct_change(1)
    frame["ret_3"] = grouped["close"].pct_change(3)
    frame["ret_5"] = grouped["close"].pct_change(5)
    frame["momentum_10"] = grouped["close"].transform(lambda series: series / series.shift(10) - 1.0)
    frame["momentum_20"] = grouped["close"].transform(lambda series: series / series.shift(20) - 1.0)
    frame["volatility_10"] = grouped["close"].transform(
        lambda series: series.pct_change().rolling(10).std()
    )
    volume_mean = grouped["volume"].transform(lambda series: series.rolling(10).mean())
    volume_std = grouped["volume"].transform(lambda series: series.rolling(10).std())
    frame["volume_z_10"] = (frame["volume"] - volume_mean) / volume_std.replace(0, np.nan)
    frame["forward_return_1"] = grouped["close"].shift(-1) / frame["close"] - 1.0

    frame[FEATURE_COLUMNS] = frame[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    return frame


def feature_matrix(frame: pd.DataFrame) -> np.ndarray:
    return frame.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
