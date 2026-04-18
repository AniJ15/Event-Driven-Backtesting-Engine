from __future__ import annotations

import math

import pandas as pd


def compute_metrics(equity_curve: pd.DataFrame, total_trade_notional: float) -> dict[str, float]:
    if equity_curve.empty:
        return {}

    frame = equity_curve.copy().sort_values("timestamp").reset_index(drop=True)
    frame["returns"] = frame["total_equity"].pct_change().fillna(0.0)
    frame["cum_return"] = frame["total_equity"] / frame["total_equity"].iloc[0] - 1.0
    frame["rolling_peak"] = frame["total_equity"].cummax()
    frame["drawdown"] = frame["total_equity"] / frame["rolling_peak"] - 1.0

    mean_return = frame["returns"].mean()
    std_return = frame["returns"].std(ddof=0)
    periods_per_year = 252.0

    sharpe = 0.0 if std_return == 0 else math.sqrt(periods_per_year) * mean_return / std_return
    volatility = std_return * math.sqrt(periods_per_year)
    avg_equity = frame["total_equity"].mean()
    turnover = 0.0 if avg_equity == 0 else total_trade_notional / avg_equity

    return {
        "cumulative_return": round(frame["cum_return"].iloc[-1], 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(frame["drawdown"].min(), 4),
        "annualized_volatility": round(volatility, 4),
        "turnover": round(turnover, 4),
    }
