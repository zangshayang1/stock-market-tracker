# market-tracker

A Python CLI tool that monitors stock prices in near-real-time (Yahoo Finance, ~15-min delay), fires rule-based SMS alarms via AWS SNS, and backtests investment strategies with standard performance metrics.

---

## Quick Start

### 1. Install

```bash
# Install dependencies (creates .venv automatically)
python3.11 -m uv sync

# Install dev dependencies (pytest, ruff, mypy, moto)
python3.11 -m uv sync --extra dev
```

### 2. Configure AWS credentials

Copy `.env.example` to `.env` and fill in your AWS credentials and target phone number:

```bash
cp .env.example .env
```

```dotenv
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=us-east-1
SNS_PHONE_NUMBER=+15551234567   # E.164 format
```

The `.env` file is loaded automatically at startup. Alternatively, export the variables in your shell.

### 3. Run tests

```bash
python3.11 -m uv run pytest tests/unit/ -v
```

---

## Part 1: How to Use Each Feature

### Starting the Monitor

```bash
# Start the polling daemon (blocking — runs until Ctrl-C or SIGTERM)
market-tracker monitor start --config configs/alarms.example.yaml

# Custom poll interval (default: 60 seconds)
market-tracker monitor start --config configs/alarms.yaml --interval 30

# Verbose logging
market-tracker monitor start --config configs/alarms.yaml --verbose
```

The daemon writes its PID to `~/.market-tracker/monitor.pid` and removes it on clean shutdown. Send `SIGTERM` or `Ctrl-C` to stop cleanly.

```bash
# Check current alarm suppression state without starting the daemon
market-tracker monitor status --config configs/alarms.yaml
```

```
┌──────────────────────┬──────────┬─────────────────────┬────────────────┬────────────┐
│ Alarm                │ Cooldown │ Last Fired          │ Silenced Until │ Status     │
├──────────────────────┼──────────┼─────────────────────┼────────────────┼────────────┤
│ QQQ Large Daily Drop │ 120m     │ 2026-02-27 14:30 UTC│ —              │ SUPPRESSED │
│ AAPL RSI Oversold    │ 240m     │ —                   │ —              │ ACTIVE     │
└──────────────────────┴──────────┴─────────────────────┴────────────────┴────────────┘
```

---

### Configuring Alarms

Create a YAML file (or edit `configs/alarms.example.yaml`). Each alarm has a name, cooldown, a logic gate, and one or more rules.

**Alarm skeleton:**

```yaml
alarms:
  - name: "My Alarm"        # unique name — used as state key
    cooldown_minutes: 60    # minimum minutes between firings
    logic: ANY              # ANY = OR across rules, ALL = AND
    rules:
      - id: "unique-rule-id"
        type: <rule_type>
        symbol: AAPL
        params:
          # rule-specific params (see below)
```

#### Rule type reference

**`day_change_pct`** — fires when today's % change vs a reference price exceeds a threshold.

```yaml
type: day_change_pct
symbol: QQQ
params:
  direction: down        # "up" or "down"
  threshold_pct: 2.0     # percentage (positive number)
  reference: prev_close  # "prev_close" or "open"
```

Fires if: `(last_price - prev_close) / prev_close * 100 <= -2.0` (for `direction: down`).

---

**`nday_change_pct`** — fires when price has moved by a threshold over N trading days.

```yaml
type: nday_change_pct
symbol: QQQ
params:
  direction: down
  threshold_pct: 5.0
  n_days: 5
```

---

**`price_threshold`** — fires when price crosses above or below a fixed level.

```yaml
type: price_threshold
symbol: SPY
params:
  direction: below       # "above" or "below"
  level: 500.0
  require_cross: true    # true = only fire on transition; false = fire while below
```

When `require_cross: true`, the rule only fires on the *first* bar that crosses the level, not on every subsequent bar while price remains on that side. This is tracked in state.

---

**`rsi`** — fires when the 14-day RSI is overbought or oversold.

```yaml
type: rsi
symbol: AAPL
params:
  condition: oversold    # "oversold" or "overbought"
  threshold: 30          # fire when RSI <= 30 (oversold) or RSI >= threshold (overbought)
  period: 14             # optional, default 14
```

---

**`volume_spike`** — fires when today's volume is ≥ N× the 30-day average.

```yaml
type: volume_spike
symbol: NVDA
params:
  multiplier: 3.0        # today's volume / 30-day avg >= 3.0
  window: 30             # optional, default 30
  min_time_of_day: "11:00"  # optional — suppress before this time (ET)
```

The `min_time_of_day` gate prevents false spikes from low early-morning volume before the market has meaningful activity.

---

#### AND / OR logic

`logic: ANY` — the alarm fires if **at least one** rule triggers (OR).
`logic: ALL` — the alarm fires only if **every** rule triggers simultaneously (AND).

```yaml
# Fires only when BOTH conditions are true at the same time
- name: "QQQ Confirmed Crash"
  logic: ALL
  rules:
    - id: "drop-3pct"
      type: day_change_pct
      symbol: QQQ
      params: { direction: down, threshold_pct: 3.0, reference: prev_close }
    - id: "rsi-oversold"
      type: rsi
      symbol: QQQ
      params: { condition: oversold, threshold: 35 }
```

---

#### Test, list, and silence alarms

```bash
# Pretty-print all loaded alarms and their rules
market-tracker alarm list --config configs/alarms.yaml

# One-shot evaluation against live market data (no SMS sent)
market-tracker alarm test --config configs/alarms.yaml

# Evaluate AND send SMS for triggered alarms
market-tracker alarm test --config configs/alarms.yaml --send-alert

# Silence an alarm for 8 hours (useful after market events you already know about)
market-tracker alarm silence "QQQ Large Daily Drop" --hours 8
```

---

### Running a Backtest

```bash
# Run with the example config and print the metrics table
market-tracker backtest run --config configs/backtest.example.yaml

# Save the full result (including trade log) to a JSON file
market-tracker backtest run --config configs/backtest.yaml --output result.json

# Re-render a previously saved result
market-tracker backtest report result.json
```

**Example output:**

```
         Backtest — QQQ (2020-01-01 → 2024-12-31)
┌──────────────────┬───────────┐
│ Metric           │ Value     │
├──────────────────┼───────────┤
│ Initial Capital  │ $10,000   │
│ Final Capital    │ $12,340   │
│ Total Return     │ +23.40%   │
│ Max Drawdown     │ 18.50%    │
│ Longest Drawdown │ 87 days   │
│ Sharpe Ratio     │ 0.812     │
│ Win Rate         │ 61.3%     │
│ Profit Factor    │ 2.14      │
│ Avg Win          │ +3.21%    │
│ Avg Loss         │ -2.87%    │
│ Total Trades     │ 31        │
│ Winning Trades   │ 19        │
│ Losing Trades    │ 12        │
└──────────────────┴───────────┘
```

#### Backtest config reference

```yaml
backtest:
  symbol: QQQ
  start_date: "2020-01-01"
  end_date: "2024-12-31"
  initial_capital: 10000.00
  commission_per_trade: 1.00       # flat $ per trade (applied on both entry and exit)
  strategy:
    type: dip_buy
    params:
      entry_condition:
        type: day_change_pct
        direction: down
        threshold_pct: 2.0         # buy when daily drop >= 2%
        reference: prev_close
      shares_per_trade: 10
      exit_condition:
        type: day_change_pct
        direction: up
        threshold_pct: 3.0         # sell when price recovers 3% from entry
        reference: entry_price
      max_open_positions: 5        # never hold more than 5 simultaneous positions
      stop_loss_pct: 5.0           # hard stop-loss at 5% below entry price
```

Exit priority per bar: **stop-loss is checked first**, then the target exit condition.

---

## Part 2: Component Walkthrough

### Architecture overview

```
CLI (cli.py)
  ├── monitor start  ──────────────────────────┐
  │                                            ▼
  │                                    Daemon (daemon.py)
  │                                       │
  │                              ┌────────┴────────┐
  ▼                               ▼                 ▼
Config (config.py)         Exchange-calendars   Cache (cache.py)
  └── Pydantic models            (NYSE open?)        │
       (models.py)                               Fetcher (fetcher.py)
                                                  (yfinance)
                                                      │
                                              ┌───────┴──────────┐
                                              ▼                  ▼
                                         Indicators          Rule eval
                                         rsi.py              price_rules.py
                                         volume.py           rsi_rules.py
                                                             volume_rules.py
                                                                  │
                                                            Evaluator (evaluator.py)
                                                            AND/OR logic
                                                                  │
                                                       ┌──────────┴──────────┐
                                                       ▼                     ▼
                                               State (state.py)       SNS (sns.py)
                                               dedup / cooldown        SMS alert
```

---

### Layer 1 — Configuration & Models (`config.py`, `models.py`)

`config.py` is the only entrypoint for reading YAML. It calls `yaml.safe_load` then passes the raw dict to Pydantic for validation. Any missing required fields, wrong types, or unknown rule types will raise a `ValueError` with a clear message before any network calls are made.

`models.py` defines all data shapes as Pydantic v2 `BaseModel` classes:

| Model | Purpose |
|---|---|
| `RuleConfig` | One rule's type, symbol, and params |
| `AlarmConfig` | Named alarm with cooldown, logic, and rule list |
| `AlarmState` | Per-alarm dedup state (last_fired, silenced_until, last_side) |
| `BacktestConfig` | Full backtest spec including strategy params |
| `BacktestResult` | All output metrics plus the full trade log |

Models are the boundary between YAML-on-disk and Python objects. Nothing downstream touches raw dicts.

---

### Layer 2 — Data (`data/fetcher.py`, `data/cache.py`)

**`fetcher.py`** is the only file in the codebase that imports `yfinance`. This isolation means swapping the data source requires changing exactly one file.

- `fetch_history(symbol, period, interval)` — returns a pandas DataFrame with adjusted OHLCV data. On HTTP 429 it backs off exponentially (2s → 4s → 8s → 16s) then returns an empty DataFrame. All other errors are also caught and return empty — the daemon never crashes due to a data fetch failure.
- `fetch_quote(symbol)` — returns a lightweight `fast_info` dict (last price, prev close, open, day volume) suitable for intraday rule checks.

**`cache.py`** wraps both fetch functions with a `TTLCache` (55-second TTL, 256 slots). Within a single polling cycle, if multiple alarms reference the same symbol, only one yfinance call is made. The cache is explicitly cleared at the end of each cycle so the next cycle always gets fresh data.

---

### Layer 3 — Indicators (`indicators/rsi.py`, `indicators/volume.py`)

Pure pandas math — no TA-Lib dependency.

**RSI (`rsi.py`):**
Implements Wilder's original SMMA using `pandas.ewm(alpha=1/period, adjust=False)`. The smoothing factor `alpha=1/14 ≈ 0.0714` matches Wilder's definition exactly. The first `period-1` values are set to NaN since the warm-up period produces unreliable values. When `avg_loss = 0` with positive gains (pure uptrend), RSI correctly returns 100 rather than NaN.

**Volume (`volume.py`):**
`rolling_avg_volume(volume, window=30)` computes a `min_periods=window` rolling mean, so it only produces values when a full window is available. `is_volume_spike` computes the baseline from all bars *except* today (i.e., `volume.iloc[:-1]`), preventing today's spike from inflating its own baseline.

---

### Layer 4 — Rules (`rules/`)

Every rule is a class that inherits `BaseRule` and implements `evaluate() → (bool, str)`. The bool is whether the condition is met; the string is a human-readable description of the result (used in SMS text and log output).

`rules/factory.py` maps rule type strings from YAML to classes:

```
"day_change_pct"  → DayChangePctRule
"nday_change_pct" → NDayChangePctRule
"price_threshold" → PriceThresholdRule
"rsi"             → RSIRule
"volume_spike"    → VolumeSpikeRule
```

Each rule pulls data from the **cache**, not from the fetcher directly. This means rules are automatically deduplicated at the data layer.

`PriceThresholdRule` is a special case: its `evaluate()` takes an optional `last_side` parameter and returns a third value — `new_side` — so the evaluator can pass current state in and get updated state back without the rule needing to know about persistence.

---

### Layer 5 — Alarm Evaluator (`alarms/evaluator.py`)

`evaluate_alarm(alarm, last_sides)` iterates over the alarm's rules, builds each via the factory, calls `evaluate()`, and collects `(triggered, message)` pairs. At the end it applies the `logic` gate:

- `ANY` — triggered if at least one rule fired
- `ALL` — triggered only if every rule fired

Errors inside individual rule evaluations are caught and logged; they do not propagate. A failing rule is treated as not-triggered so one bad symbol can't take down evaluations for all others.

`PriceThreshold` side updates are collected in `new_sides` and returned from `evaluate_alarm` regardless of whether the alarm triggered, so the state manager can persist them on every cycle.

---

### Layer 6 — Alarm State (`alarms/state.py`)

Deduplication happens in three layers, in this precedence order:

**1. Silence** — `alarm silence` writes `silenced_until` (a UTC timestamp) to the state file. While `now < silenced_until`, the alarm is fully suppressed regardless of cooldown.

**2. Cooldown window** — After an alarm fires, `last_fired` is written. The alarm is suppressed for `cooldown_minutes` after that timestamp. This prevents SMS flooding if a condition persists across many polling cycles.

**3. Side tracking** — For `price_threshold` rules with `require_cross: true`, the evaluator tracks whether price was last seen `above` or `below` the level. The rule only fires on a *transition* — not on every bar while price stays on one side. Side state is persisted even when an alarm doesn't fire, so the tracking survives daemon restarts.

**Atomic writes:** The state file at `~/.market-tracker/alarm_state.json` is written using `tempfile.mkstemp` → `os.replace`. This guarantees the file is never in a partially-written state, even if the process receives SIGTERM mid-write.

**SNS-first update ordering:** If the SNS send fails, `record_fired` is *not* called. The state remains as if the alarm never fired, so the next polling cycle will retry. This ensures no alert is lost silently.

---

### Layer 7 — SNS Alerts (`alerts/sns.py`)

`send_sms(message, phone_number)` publishes via `boto3` to a direct phone number (not a topic). SMS messages are capped at 155 characters before encoding and truncated with `…` if longer to stay within carrier limits.

On failure, it retries with exponential backoff (2s, 4s, 8s) for up to 4 total attempts before returning `False`. The caller (daemon) uses the return value to decide whether to update dedup state.

`send_health_alert` is a separate function called by the daemon when 10 consecutive polling cycles all fail — it sends a diagnostic SMS so you know the tool itself is degraded.

---

### Layer 8 — Polling Daemon (`monitor/daemon.py`)

The daemon uses APScheduler's `BlockingScheduler` with a single `interval` job. Each poll cycle:

1. **Market hours check** — `exchange_calendars.get_calendar("XNYS")` checks NYSE open/close including holidays and early-close days. Cycles outside market hours return immediately without touching the network.
2. **Per-alarm loop** — for each alarm in the config, checks suppression state first. If suppressed, skips. Otherwise calls the evaluator.
3. **Side state persistence** — even for alarms that don't trigger, side updates from `PriceThreshold` rules are written to the state file.
4. **Conditional alert** — only sends SMS if `evaluate_alarm` returned `triggered=True` and the alarm isn't suppressed. Only updates `last_fired` if the SMS send succeeded.
5. **Failure tracking** — a consecutive failure counter increments when any alarm's evaluation throws an unhandled exception. At 10 consecutive failure cycles, a health SMS is sent and the counter resets.
6. **Cache flush** — `data_cache.clear_cache()` is called at the end of every cycle so the next cycle fetches fresh data.

---

### Layer 9 — Backtest Engine (`backtest/engine.py`, `strategy.py`, `metrics.py`)

The engine is event-driven: it iterates over daily OHLCV bars in chronological order, processes exits before entries on each bar (to avoid same-bar buy-then-sell), and maintains an equity curve.

**`strategy.py` — DipBuy:**
Entry and exit conditions are evaluated against each bar using the same condition format as alarm rules. Entry fires when `day_change_pct` is below the threshold vs the previous close. Exit fires when the close is up by `threshold_pct` from entry price (target), or down by `stop_loss_pct` from entry price (stop-loss). Stop-loss is checked first.

**`metrics.py`:**

| Metric | Calculation |
|---|---|
| Total return % | `(final - initial) / initial * 100` |
| Max drawdown % | Peak-to-trough drop on the equity curve, expressed as a positive number |
| Longest drawdown days | Longest consecutive period where equity is below a prior peak |
| Sharpe ratio | Annualized: `mean(excess_daily_returns) / std(excess_daily_returns) * sqrt(252)`. Risk-free rate defaults to 4.25% annual |
| Win rate | Winning trades (pnl > 0) / total closed trades |
| Profit factor | Gross profit / gross loss across all trades |
| Avg win / avg loss | Mean `pnl_pct` for winning / losing trades respectively |

All positions still open at `end_date` are closed at the final bar's close price with `exit_reason: end_of_data`.

---

## File Structure

```
investment-tools/
├── pyproject.toml
├── .env.example
├── .gitignore
├── configs/
│   ├── alarms.example.yaml
│   └── backtest.example.yaml
├── tasks/
│   ├── todo.md
│   └── lessons.md
├── tests/
│   ├── conftest.py
│   └── unit/
│       ├── test_rsi.py
│       ├── test_volume.py
│       ├── test_rules.py
│       ├── test_alarms.py
│       ├── test_sns.py
│       └── test_backtest.py
└── src/
    └── market_tracker/
        ├── cli.py
        ├── config.py
        ├── models.py
        ├── data/
        │   ├── fetcher.py        # only yfinance import
        │   └── cache.py          # TTLCache (55s)
        ├── indicators/
        │   ├── rsi.py            # Wilder's SMMA
        │   └── volume.py         # rolling avg + spike
        ├── rules/
        │   ├── base.py
        │   ├── factory.py
        │   ├── price_rules.py    # day_change_pct, nday_change_pct, price_threshold
        │   ├── rsi_rules.py
        │   └── volume_rules.py
        ├── alarms/
        │   ├── evaluator.py      # AND/OR logic
        │   └── state.py          # cooldown, silence, side-tracking; atomic writes
        ├── alerts/
        │   └── sns.py            # boto3 SNS, retry, truncation
        ├── monitor/
        │   └── daemon.py         # APScheduler, market hours, PID file
        └── backtest/
            ├── engine.py
            ├── strategy.py
            └── metrics.py
```

---

## CLI Reference

```
market-tracker monitor start    [--config FILE] [--interval SECS] [--verbose]
market-tracker monitor status   [--config FILE]
market-tracker alarm list       [--config FILE]
market-tracker alarm test       [--config FILE] [--send-alert] [--verbose]
market-tracker alarm silence    NAME [--hours N]
market-tracker backtest run     [--config FILE] [--output FILE] [--verbose]
market-tracker backtest report  FILE
```
