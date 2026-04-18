# Event-Driven Backtesting Engine

A modular, event-driven trading simulation engine inspired by production trading systems.

This project models the full lifecycle of a trade:

`market data -> strategy signal -> portfolio order -> execution fill -> portfolio/PnL update`

The goal is realism and extensibility, not just return calculation.

## Implemented in this first version

- Event-driven architecture with explicit `MarketEvent`, `SignalEvent`, `OrderEvent`, and `FillEvent`
- CSV-based historical market data feed
- Single-symbol moving-average crossover strategy
- Portfolio accounting with cash, positions, average cost, realized PnL, unrealized PnL, and equity tracking
- Execution simulation with:
  - latency
  - slippage
  - spread costs
  - fixed + percentage commissions
  - partial fills based on bar volume participation
- Performance analytics:
  - cumulative return
  - Sharpe ratio
  - max drawdown
  - annualized volatility
  - turnover

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
  strategy/
    base.py
    moving_average.py
  events.py
  main.py
sample_data/
  AAPL.csv
requirements.txt
```

## Quick start

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the sample backtest:

```bash
python -m engine.main --csv sample_data/AAPL.csv --symbol AAPL
```

## Example output

The engine prints:

- a performance summary
- final portfolio state
- recent fills
- the tail of the equity curve

## Architecture overview

### Events

All state changes move through an in-memory event queue:

- `MarketEvent`: emitted by the data handler for each new bar
- `SignalEvent`: emitted by the strategy
- `OrderEvent`: emitted by the portfolio
- `FillEvent`: emitted by the execution engine

### Main loop

For each bar:

1. Data handler emits a `MarketEvent`
2. Execution engine checks whether delayed orders can now fill
3. Portfolio marks positions to market
4. Strategy consumes market data and emits signals
5. Portfolio turns signals into orders
6. Broker turns orders into fills
7. Portfolio updates positions, cash, and PnL

## Current limitations

- Single-symbol demo strategy
- Bar-based simulation, not tick-level
- No live broker integration yet
- No dedicated risk engine yet

## Suggested next steps

- Add multi-asset support
- Add limit-order persistence and cancel/replace workflows
- Add a risk layer with exposure limits and drawdown controls
- Add benchmark comparison and plotting
- Add Numba optimization for hot paths

## Resume-ready description

Designed and implemented a modular, event-driven backtesting engine simulating production trading workflows from market data ingestion through signal generation, order management, execution, and portfolio accounting. Built realistic execution models including slippage, spread, latency, commissions, and partial fills, and added analytics for PnL, turnover, drawdown, and Sharpe ratio.
