# Event-Driven Backtesting Engine

A modular, event-driven trading simulation engine that now acts like a small strategy research lab.

This version supports:

- multi-asset event-driven simulation
- 5 to 6 years of bundled sample data
- train/test splits over time
- multiple technical and ML-style strategies
- out-of-sample comparison across strategies
- a live local app for comparing test-set results

## What it does now

The engine trains each strategy on the first part of the historical data and then tests that strategy on the later part of the data using the full event-driven trading simulation.

That means the workflow is:

`historical data -> train models/strategy state -> replay test set through event engine -> compare out-of-sample results`

## Included strategies

- `moving_average`
  - moving-average crossover trend strategy
- `mean_reversion`
  - z-score mean reversion strategy
- `linear_regression`
  - predicts next-bar return from engineered features
- `logistic_regression`
  - predicts up/down direction from engineered features

## Features used by the ML-style strategies

The regression/classification strategies train on features such as:

- 1-day return
- 3-day return
- 5-day return
- 10-day momentum
- 20-day momentum
- 10-day volatility
- 10-day volume z-score

## Risk controls

The backtest still includes:

- per-symbol exposure caps
- gross leverage cap
- stop-loss exits
- max drawdown portfolio de-risking

## Data

The bundled sample data now includes roughly 7 calendar years of daily business-day bars from `2018-01-02` through `2024-12-31` for:

- `AAPL`
- `MSFT`
- `SPY`
- `QQQ`
- `NVDA`
- `AMZN`

Each file is in `sample_data/` and uses:

```text
timestamp,open,high,low,close,volume
```

## Project structure

```text
engine/
  analytics/
    metrics.py
  data/
    data_handler.py
  execution/
    broker.py
  portfolio/
    portfolio.py
  risk/
    engine.py
  strategy/
    base.py
    features.py
    mean_reversion.py
    ml_models.py
    moving_average.py
    router.py
  app.py
  events.py
  main.py
  reporting.py
sample_data/
  AAPL.csv
  AMZN.csv
  MSFT.csv
  NVDA.csv
  QQQ.csv
  SPY.csv
```

## Run the comparison suite

From the repo root:

```bash
python3 -m engine.main \
  --data-dir sample_data \
  --symbols AAPL,MSFT,SPY,QQQ,NVDA,AMZN \
  --train-ratio 0.7
```

By default, that compares:

- `moving_average`
- `mean_reversion`
- `linear_regression`
- `logistic_regression`

You can limit the suite:

```bash
python3 -m engine.main \
  --data-dir sample_data \
  --symbols AAPL,MSFT,SPY \
  --strategies moving_average,linear_regression \
  --train-ratio 0.75
```

The CLI prints:

- train/test split details
- side-by-side strategy comparison on the test set

It also writes:

```text
artifacts/backtest_results.json
```

## Run the live local app

```bash
python3 -m engine.app \
  --data-dir sample_data \
  --symbols AAPL,MSFT,SPY,QQQ,NVDA,AMZN \
  --train-ratio 0.7
```

Then open:

```text
http://127.0.0.1:8000
```

## What the app shows

- train/test split summary
- test-set comparison table across strategies
- overlaid equity curves for each strategy on the test set
- selected-strategy metrics
- training summary for the selected model/strategy
- per-symbol test metrics
- portfolio state by symbol
- risk events
- recent fills

You can:

- filter by strategy
- filter by symbol
- refresh the current view
- rerun the full train/test suite
- auto-refresh the dashboard
