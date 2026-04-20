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


def compute_symbol_metrics(
    market_data: pd.DataFrame,
    fills_frame: pd.DataFrame,
    symbol_summary: pd.DataFrame,
) -> pd.DataFrame:
    if market_data.empty:
        return pd.DataFrame()

    rows: list[dict[str, float | int | str]] = []
    fills_by_symbol = (
        fills_frame.groupby("symbol").agg(trade_count=("quantity", "count")) if not fills_frame.empty else None
    )
    summary_lookup = symbol_summary.set_index("symbol") if not symbol_summary.empty else pd.DataFrame()

    for symbol, group in market_data.groupby("symbol"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        buy_hold_return = group["close"].iloc[-1] / group["close"].iloc[0] - 1.0
        trade_count = 0 if fills_by_symbol is None or symbol not in fills_by_symbol.index else int(
            fills_by_symbol.loc[symbol, "trade_count"]
        )

        realized = 0.0
        unrealized = 0.0
        position = 0
        if not summary_lookup.empty and symbol in summary_lookup.index:
            row = summary_lookup.loc[symbol]
            realized = float(row["realized_pnl"])
            unrealized = float(row["unrealized_pnl"])
            position = int(row["position"])

        rows.append(
            {
                "symbol": symbol,
                "buy_hold_return": round(buy_hold_return, 4),
                "trade_count": trade_count,
                "position": position,
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": round(unrealized, 2),
            }
        )

    return pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)
