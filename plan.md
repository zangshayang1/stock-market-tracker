# Investment Monitor — Implementation Plan

## Context
Build a Python CLI tool that monitors stock prices in near-real-time (Yahoo Finance free tier, ~15-min delay), fires rule-based alarms via AWS SNS SMS, and backtests investment strategies with standard performance metrics.

---

## Tech Stack
- **Python 3.11+**, `uv` for env management, `hatchling` build backend
- **yfinance** — stock data (free, unlimited, 15-min delay)
- **boto3** — AWS SNS SMS alerts
- **typer + rich** — CLI interface
- **pydantic v2** — config schema validation
- **APScheduler 3.x** — polling daemon (blocking, synchronous)
- **exchange-calendars** — authoritative NYSE trading hours/holidays
- **pandas + numpy** — data processing and indicator math (no TA-Lib)
- **cachetools** — TTLCache for per-symbol data (55s TTL)

---

## Project Structure

```
investment-tools/
├── pyproject.toml
├── .env.example                        # AWS creds template
├── .gitignore
├── configs/
│   ├── alarms.example.yaml
│   └── backtest.example.yaml
├── tasks/
│   ├── todo.md
│   └── lessons.md
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/                    # vcrpy cassettes for yfinance
└── src/
    └── investment_monitor/
        ├── cli.py                      # Typer app — all CLI commands
        ├── config.py                   # YAML loading + Pydantic validation
        ├── models.py                   # Rule, AlarmConfig, AlarmFiredEvent, BacktestResult
        ├── data/
        │   ├── fetcher.py              # yfinance wrapper (ONLY place yfinance is imported)
        │   └── cache.py                # TTLCache keyed by (symbol, interval)
        ├── indicators/
        │   ├── rsi.py                  # Wilder's SMMA RSI in pure pandas
        │   └── volume.py               # Rolling avg volume, spike detection
        ├── rules/
        │   ├── base.py                 # Abstract BaseRule → evaluate() → (bool, str)
        │   ├── price_rules.py          # day_change_pct, nday_change_pct, price_threshold
        │   ├── rsi_rules.py            # overbought / oversold
        │   └── volume_rules.py         # volume_spike
        ├── alarms/
        │   ├── evaluator.py            # Runs all rules, applies AND/OR logic
        │   └── state.py                # Dedup: cooldown, side-tracking, silence; atomic JSON writes
        ├── alerts/
        │   └── sns.py                  # boto3 SNS publisher with retry + truncation
        ├── monitor/
        │   └── daemon.py               # APScheduler BlockingScheduler, PID file, SIGTERM handler
        └── backtest/
            ├── engine.py               # Event-driven daily-bar loop, Portfolio class
            ├── strategy.py             # Strategy config → signal logic
            └── metrics.py              # Sharpe, max drawdown, win rate, total return
```

---

## Alarm Rule Types (all supported)

| Type | Description |
|---|---|
| `day_change_pct` | % change today vs `open` or `prev_close` |
| `nday_change_pct` | % change over N trading days |
| `price_threshold` | Price crosses above/below a fixed level (`require_cross` flag for edge detection) |
| `rsi` | 14-day RSI overbought (>threshold) or oversold (<threshold) |
| `volume_spike` | Today's volume ≥ N× 30-day average |

Alarms support `logic: ANY | ALL` (OR vs AND across rules), `cooldown_minutes`, and a `silence` CLI command.

### Example YAML
```yaml
alarms:
  - name: "QQQ Large Daily Drop"
    cooldown_minutes: 120
    logic: ANY
    rules:
      - id: "qqq-day-drop-2pct"
        type: day_change_pct
        symbol: QQQ
        params:
          direction: down
          threshold_pct: 2.0
          reference: prev_close
```

---

## Deduplication (3-layer)
1. **Cooldown window** — `last_fired` timestamp in `~/.investment-monitor/alarm_state.json`; alarm suppressed until `cooldown_minutes` elapsed
2. **Side tracking** — `price_threshold` rules with `require_cross: true` track last known side; only fire on transition
3. **Silence command** — `investment-monitor alarm silence "NAME" --hours N` writes `silenced_until` to state file

State file written atomically: `tempfile` → `os.replace()`.

---

## Polling Daemon

```
$ investment-monitor monitor start [--config alarms.yaml] [--interval 60]
```

**Each 60s cycle:**
1. Check NYSE market hours (`exchange_calendars`) → skip if closed
2. Collect unique symbols from all alarm configs
3. Batch-fetch market data (TTL cache prevents redundant calls)
4. Evaluate all rules per alarm; apply AND/OR logic
5. For triggered alarms: check dedup state → send SNS → update state
6. Log summary (N rules evaluated, M alarms fired, elapsed ms)

**Resilience:** All network/API errors caught; daemon never crashes. After 10 consecutive all-symbol failures, sends a system health SNS alert.

---

## CLI Commands

```
investment-monitor monitor start     # Start polling daemon (blocking)
investment-monitor monitor status    # Show active alarms and dedup state
investment-monitor alarm list        # Pretty-print loaded rules
investment-monitor alarm test        # One-shot dry-run evaluation
investment-monitor alarm silence     # Silence an alarm for N hours
investment-monitor backtest run      # Run backtest; print metrics table
investment-monitor backtest report   # Load saved result JSON and render
```

---

## Backtesting Engine

Daily-bar event-driven loop over yfinance OHLCV history.

**Strategy config:**
```yaml
backtest:
  symbol: QQQ
  start_date: "2020-01-01"
  end_date: "2024-12-31"
  initial_capital: 10000.00
  commission_per_trade: 1.00
  strategy:
    type: dip_buy
    params:
      entry_condition:
        type: day_change_pct
        direction: down
        threshold_pct: 2.0
        reference: prev_close
      shares_per_trade: 10
      exit_condition:
        type: day_change_pct
        direction: up
        threshold_pct: 3.0
        reference: entry_price
      max_open_positions: 5
      stop_loss_pct: 5.0
```

**Output metrics:**
- Total return %
- Max drawdown % + longest drawdown days
- Win rate % (profitable closed trades / total)
- Sharpe ratio (annualized, configurable risk-free rate default 4.25%)
- Profit factor, avg win/loss %, full trade log

---

## Key Edge Cases Handled
- **Market closed:** Skip poll; no stale data alarms during off-hours
- **Bad data (price=0, empty DataFrame):** Skip symbol, log warning; no crash
- **Split/dividend:** `auto_adjust=True` on all yfinance calls
- **HTTP 429:** Exponential backoff (2s → 4s → 8s → 16s), then skip cycle
- **SNS failure:** Do NOT update dedup state if alert unsent (will retry next poll)
- **Insufficient backtest capital:** Skip entry, log warning
- **Volume rules before 11 AM ET:** Configurable `min_time_of_day` param

---

## Dependencies (`pyproject.toml`)
```
yfinance>=1.0.0, pandas>=2.2.0, numpy>=1.26.0,
typer>=0.12.0, rich>=13.7.0, pyyaml>=6.0.1,
pydantic>=2.6.0, python-dotenv>=1.0.0,
apscheduler>=3.10.4, exchange-calendars>=4.5.0,
boto3>=1.34.0, cachetools>=5.3.0

[dev]: pytest, pytest-cov, vcrpy, ruff, mypy, boto3-stubs[sns]
```

---

## Build Sequence (each phase independently testable)
1. **Foundation** — `pyproject.toml`, `models.py`, `config.py`, example YAMLs
2. **Data layer** — `fetcher.py`, `cache.py` (vcrpy cassettes for tests)
3. **Indicators** — `rsi.py`, `volume.py` (unit tests vs known values)
4. **Rules** — all rule classes with boundary-condition unit tests
5. **Alarms** — `evaluator.py`, `state.py` (dedup logic tests)
6. **Alerts** — `sns.py` (moto mock for tests)
7. **CLI + Daemon** — `cli.py`, `daemon.py` (subprocess integration test)
8. **Backtesting** — `engine.py`, `metrics.py` (verify metrics vs manual calc)

---

## Verification
- `pytest tests/unit/` — all rule, indicator, and metric logic tested with synthetic data
- `pytest tests/integration/` — fetcher tested via vcrpy cassettes (no live API)
- `investment-monitor alarm test` — dry-run against live market data
- `investment-monitor backtest run --config configs/backtest.example.yaml` — verify metrics output
- Send test SNS alert via `investment-monitor alarm test --send-alert`
