from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine.main import build_run_configuration, execute_backtest


class BacktestAppState:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.latest_report: dict[str, object] | None = None
        self.latest_report_path: str | None = None

    def run_backtest(self) -> dict[str, object]:
        results = execute_backtest(**self.config)
        self.latest_report = results["payload"]
        self.latest_report_path = str(results["json_path"])
        return {
            "json_path": self.latest_report_path,
            "comparison_rows": len(results["comparison_frame"]),
            "split_info": results["split_info"],
        }


def create_handler(state: BacktestAppState) -> type[BaseHTTPRequestHandler]:
    class BacktestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(_app_html())
                return

            if parsed.path == "/api/results":
                if state.latest_report is None:
                    state.run_backtest()
                strategy = parse_qs(parsed.query).get("strategy", [None])[0]
                symbol = parse_qs(parsed.query).get("symbol", [None])[0]
                payload = _filter_payload(state.latest_report, strategy, symbol)
                self._send_json(payload)
                return

            if parsed.path == "/api/health":
                self._send_json({"status": "ok", "report_path": state.latest_report_path})
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/run":
                self._send_json(state.run_backtest())
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return BacktestHandler


def _filter_payload(
    payload: dict[str, object],
    strategy_name: str | None,
    symbol: str | None,
) -> dict[str, object]:
    filtered = {key: value for key, value in payload.items() if key != "experiments"}
    experiments = [
        {
            key: (list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value)
            for key, value in experiment.items()
        }
        for experiment in payload["experiments"]
    ]
    if strategy_name and strategy_name != "ALL":
        experiments = [
            experiment for experiment in experiments if experiment["strategy_name"] == strategy_name
        ]

    if symbol and symbol != "ALL":
        symbol = symbol.upper()
        for experiment in experiments:
            experiment["fills"] = [row for row in experiment["fills"] if row["symbol"] == symbol]
            experiment["symbol_summary"] = [
                row for row in experiment["symbol_summary"] if row["symbol"] == symbol
            ]
            experiment["symbol_metrics"] = [
                row for row in experiment["symbol_metrics"] if row["symbol"] == symbol
            ]
            experiment["market_data"] = [
                row for row in experiment["market_data"] if row["symbol"] == symbol
            ]
            experiment["risk_log"] = [
                row for row in experiment["risk_log"] if row["symbol"] in {symbol, "PORTFOLIO"}
            ]

    filtered["experiments"] = experiments
    return filtered


def _app_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Strategy Comparison Lab</title>
  <style>
    :root {
      --bg: #f6f2e8;
      --panel: #fffdf8;
      --ink: #1a2432;
      --muted: #6b7280;
      --accent: #0f766e;
      --accent-2: #b45309;
      --accent-3: #1d4ed8;
      --line: #d8d1c4;
      --danger: #b91c1c;
      --shadow: 0 14px 34px rgba(26, 36, 50, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top left, rgba(15,118,110,0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(180,83,9,0.08), transparent 24%),
        var(--bg);
      color: var(--ink);
    }
    .shell {
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px 18px 42px;
    }
    .hero { display: grid; gap: 10px; margin-bottom: 18px; }
    .eyebrow { font-size: 12px; text-transform: uppercase; letter-spacing: 0.16em; color: var(--muted); }
    h1 { margin: 0; font-size: clamp(36px, 6vw, 62px); line-height: 0.94; max-width: 11ch; }
    .sub { margin: 0; max-width: 74ch; color: var(--muted); line-height: 1.5; }
    .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 18px 0 24px; }
    select, button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      padding: 10px 14px;
      border-radius: 999px;
      font: inherit;
      cursor: pointer;
    }
    button.primary { background: var(--accent); color: white; border-color: transparent; }
    .status { color: var(--muted); font-size: 14px; }
    .split, .comparison, .detail-grid, .tables { display: grid; gap: 18px; }
    .split { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 20px; }
    .comparison { margin-bottom: 20px; }
    .detail-grid { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); margin-bottom: 20px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }
    .panel { padding: 18px; }
    .panel h2 { margin: 0 0 12px; font-size: 20px; }
    .metric { min-height: 104px; display: grid; align-content: space-between; }
    .label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); }
    .value { font-size: 28px; font-weight: 700; }
    .chart { width: 100%; height: auto; display: block; border-radius: 12px; background: linear-gradient(180deg, rgba(255,255,255,0.65), rgba(246,242,232,0.55)); }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-family: "SFMono-Regular", Menlo, monospace; font-size: 12px; }
    th, td { padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
    .danger { color: var(--danger); }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Event-Driven Trading Simulator</div>
      <h1>Strategy Comparison Lab</h1>
      <p class="sub">Models train on the first chunk of history, then trade only on the test set. Compare test performance across technical and ML strategies, then drill into one strategy and one symbol.</p>
    </section>

    <section class="controls">
      <select id="strategyFilter"></select>
      <select id="symbolFilter"></select>
      <button id="refreshBtn">Refresh View</button>
      <button id="runBtn" class="primary">Rerun Suite</button>
      <label class="status"><input type="checkbox" id="autoRefresh" /> Auto-refresh every 10s</label>
      <span class="status" id="statusText">Loading…</span>
    </section>

    <section class="split" id="splitCards"></section>

    <section class="comparison">
      <div class="card panel">
        <h2>Test-Set Comparison</h2>
        <div class="table-wrap" id="comparisonTable"></div>
      </div>
    </section>

    <section class="detail-grid">
      <div class="card panel">
        <h2>Equity Curves on Test Set</h2>
        <div id="equityChart"></div>
      </div>
      <div class="card panel">
        <h2>Selected Strategy Metrics</h2>
        <div id="strategyMetrics"></div>
      </div>
    </section>

    <section class="tables">
      <div class="card panel">
        <h2>Training Summary</h2>
        <div class="table-wrap" id="trainingSummaryTable"></div>
      </div>
      <div class="card panel">
        <h2>Per-Symbol Test Metrics</h2>
        <div class="table-wrap" id="symbolMetricsTable"></div>
      </div>
      <div class="card panel">
        <h2>Current Test-Set Portfolio by Symbol</h2>
        <div class="table-wrap" id="symbolSummaryTable"></div>
      </div>
      <div class="card panel">
        <h2>Risk Events</h2>
        <div class="table-wrap" id="riskTable"></div>
      </div>
      <div class="card panel">
        <h2>Recent Fills</h2>
        <div class="table-wrap" id="fillsTable"></div>
      </div>
    </section>
  </main>

  <script>
    const state = {
      selectedStrategy: 'ALL',
      selectedSymbol: 'ALL',
      intervalId: null,
      payload: null
    };

    async function fetchResults() {
      const params = new URLSearchParams();
      if (state.selectedStrategy && state.selectedStrategy !== 'ALL') params.set('strategy', state.selectedStrategy);
      if (state.selectedSymbol && state.selectedSymbol !== 'ALL') params.set('symbol', state.selectedSymbol);
      const response = await fetch(`/api/results?${params.toString()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Failed to fetch results');
      return response.json();
    }

    async function rerunSuite() {
      setStatus('Running train/test suite...');
      const response = await fetch('/api/run', { method: 'POST' });
      if (!response.ok) throw new Error('Failed to rerun suite');
      await loadView();
      setStatus('Suite rerun complete.');
    }

    async function loadView() {
      const payload = await fetchResults();
      state.payload = payload;
      render(payload);
      setStatus(`Loaded ${new Date().toLocaleTimeString()}`);
    }

    function setStatus(text) {
      document.getElementById('statusText').textContent = text;
    }

    function render(payload) {
      renderStrategyFilter(payload);
      renderSymbolFilter(payload);
      renderSplit(payload.split_info || {});
      renderComparison(payload.experiments || []);
      const primaryExperiment = (payload.experiments || [])[0] || null;
      renderSelectedMetrics(primaryExperiment);
      renderTrainingSummary(primaryExperiment);
      renderTable('symbolMetricsTable', primaryExperiment?.symbol_metrics || []);
      renderTable('symbolSummaryTable', primaryExperiment?.symbol_summary || []);
      renderTable('riskTable', primaryExperiment?.risk_log || [], true);
      renderTable('fillsTable', (primaryExperiment?.fills || []).slice(-25));
      renderEquityChart(payload.experiments || []);
    }

    function renderStrategyFilter(payload) {
      const select = document.getElementById('strategyFilter');
      const names = ['ALL', ...(payload.config?.strategy_names || [])];
      select.innerHTML = names.map(name => `<option value="${name}">${name}</option>`).join('');
      select.value = state.selectedStrategy;
    }

    function renderSymbolFilter(payload) {
      const select = document.getElementById('symbolFilter');
      const symbols = ['ALL', ...Object.keys(payload.config?.data_sources || {}).sort()];
      select.innerHTML = symbols.map(symbol => `<option value="${symbol}">${symbol}</option>`).join('');
      select.value = state.selectedSymbol;
    }

    function renderSplit(splitInfo) {
      const root = document.getElementById('splitCards');
      root.innerHTML = Object.entries(splitInfo).map(([key, value]) => `
        <div class="card panel metric">
          <div class="label">${key.replaceAll('_', ' ')}</div>
          <div class="value">${value}</div>
        </div>
      `).join('');
    }

    function renderComparison(experiments) {
      const rows = experiments.map(experiment => ({
        strategy: experiment.strategy_name,
        ...experiment.metrics
      }));
      renderTable('comparisonTable', rows);
    }

    function renderSelectedMetrics(experiment) {
      const root = document.getElementById('strategyMetrics');
      if (!experiment) {
        root.innerHTML = '<p>No strategy selected.</p>';
        return;
      }
      root.innerHTML = Object.entries(experiment.metrics).map(([key, value]) => `
        <div class="card panel metric" style="margin-bottom:12px;">
          <div class="label">${key.replaceAll('_', ' ')}</div>
          <div class="value">${value}</div>
        </div>
      `).join('');
    }

    function renderTrainingSummary(experiment) {
      const summary = experiment?.training_summary || {};
      const rows = Object.entries(summary).map(([key, value]) => ({
        key,
        value: Array.isArray(value) ? value.join(', ') : JSON.stringify(value)
      }));
      renderTable('trainingSummaryTable', rows);
    }

    function renderTable(elementId, rows, isDanger = false) {
      const root = document.getElementById(elementId);
      if (!rows.length) {
        root.innerHTML = '<p>No data available.</p>';
        return;
      }
      const headers = Object.keys(rows[0]);
      root.innerHTML = `
        <table>
          <thead><tr>${headers.map(header => `<th>${header}</th>`).join('')}</tr></thead>
          <tbody>
            ${rows.map(row => `
              <tr class="${isDanger ? 'danger' : ''}">
                ${headers.map(header => `<td>${row[header] ?? ''}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function renderEquityChart(experiments) {
      const root = document.getElementById('equityChart');
      if (!experiments.length) {
        root.innerHTML = '';
        return;
      }
      const width = 760;
      const height = 280;
      const padding = 18;
      const colors = ['#0f766e', '#b45309', '#1d4ed8', '#dc2626', '#7c3aed'];
      const allValues = experiments.flatMap(exp => (exp.equity_curve || []).map(row => Number(row.total_equity)));
      const min = Math.min(...allValues);
      const max = Math.max(...allValues);
      const span = max - min || 1;
      const series = experiments.map((experiment, index) => {
        const rows = experiment.equity_curve || [];
        if (rows.length < 2) return '';
        const stepX = (width - 2 * padding) / (rows.length - 1);
        const points = rows.map((row, rowIndex) => {
          const value = Number(row.total_equity);
          const x = padding + rowIndex * stepX;
          const normalized = (value - min) / span;
          const y = height - padding - normalized * (height - 2 * padding);
          return `${x.toFixed(2)},${y.toFixed(2)}`;
        }).join(' ');
        return `<polyline fill="none" stroke="${colors[index % colors.length]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${points}"></polyline>`;
      }).join('');

      const legend = experiments.map((experiment, index) => `
        <div style="display:flex;align-items:center;gap:8px;margin:8px 14px 0 0;">
          <span style="width:14px;height:14px;border-radius:999px;background:${colors[index % colors.length]};display:inline-block;"></span>
          <span>${experiment.strategy_name}</span>
        </div>
      `).join('');

      root.innerHTML = `
        <svg class="chart" viewBox="0 0 ${width} ${height}" role="img">
          <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#b9c1cc" stroke-width="1"></line>
          ${series}
        </svg>
        <div style="display:flex;flex-wrap:wrap;margin-top:10px;">${legend}</div>
      `;
    }

    document.getElementById('strategyFilter').addEventListener('change', async event => {
      state.selectedStrategy = event.target.value;
      await loadView();
    });
    document.getElementById('symbolFilter').addEventListener('change', async event => {
      state.selectedSymbol = event.target.value;
      await loadView();
    });
    document.getElementById('refreshBtn').addEventListener('click', loadView);
    document.getElementById('runBtn').addEventListener('click', rerunSuite);
    document.getElementById('autoRefresh').addEventListener('change', event => {
      if (state.intervalId) clearInterval(state.intervalId);
      state.intervalId = event.target.checked ? setInterval(loadView, 10000) : null;
    });

    loadView().catch(error => setStatus(error.message));
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live local strategy-comparison app.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
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
    parser.add_argument("--report-json", default="artifacts/backtest_results.json", help="JSON artifact path")
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
    state = BacktestAppState(config=config)
    state.run_backtest()
    server = ThreadingHTTPServer((args.host, args.port), create_handler(state))
    print(f"Live app running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
