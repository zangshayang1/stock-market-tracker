# Market Tracker — Build Todo

## Phase 1: Foundation
- [x] pyproject.toml
- [x] models.py
- [x] config.py
- [x] .env.example, .gitignore
- [x] configs/alarms.example.yaml
- [x] configs/backtest.example.yaml

## Phase 2: Data layer
- [x] src/market_tracker/data/fetcher.py
- [x] src/market_tracker/data/cache.py

## Phase 3: Indicators
- [x] src/market_tracker/indicators/rsi.py
- [x] src/market_tracker/indicators/volume.py
- [x] tests/unit/test_rsi.py
- [x] tests/unit/test_volume.py

## Phase 4: Rules
- [x] src/market_tracker/rules/base.py
- [x] src/market_tracker/rules/price_rules.py
- [x] src/market_tracker/rules/rsi_rules.py
- [x] src/market_tracker/rules/volume_rules.py
- [x] src/market_tracker/rules/factory.py
- [x] tests/unit/test_rules.py

## Phase 5: Alarms
- [x] src/market_tracker/alarms/evaluator.py
- [x] src/market_tracker/alarms/state.py
- [x] tests/unit/test_alarms.py

## Phase 6: Alerts
- [x] src/market_tracker/alerts/sns.py
- [x] tests/unit/test_sns.py

## Phase 7: CLI + Daemon
- [x] src/market_tracker/cli.py
- [x] src/market_tracker/monitor/daemon.py

## Phase 8: Backtesting
- [x] src/market_tracker/backtest/engine.py
- [x] src/market_tracker/backtest/strategy.py
- [x] src/market_tracker/backtest/metrics.py
- [x] tests/unit/test_backtest.py

## Phase 9: Verification ✓
- [x] uv sync (72 packages installed)
- [x] pytest tests/unit/ — 72/72 passed
- [x] market-tracker --help — all 7 commands verified

## Review Notes
- RSI fix: avg_loss=0 + avg_gain>0 now correctly returns RSI=100
- Sharpe tests updated to use varied (non-identical) daily returns
- All 3 CLI sub-groups: monitor, alarm, backtest — fully functional
