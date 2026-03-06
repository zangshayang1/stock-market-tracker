"""
CLI entry point for market-tracker.

Commands:
  monitor start   — Start polling daemon (blocking)
  monitor status  — Show active alarms and dedup state
  alarm list      — Pretty-print loaded rules
  alarm test      — One-shot dry-run evaluation
  alarm silence   — Silence an alarm for N hours
  backtest run    — Run backtest; print metrics table
  backtest report — Load saved result JSON and render
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(name="market-tracker", help="Stock alarm monitor & backtester")
monitor_app = typer.Typer(help="Monitor commands")
alarm_app = typer.Typer(help="Alarm commands")
backtest_app = typer.Typer(help="Backtest commands")

app.add_typer(monitor_app, name="monitor")
app.add_typer(alarm_app, name="alarm")
app.add_typer(backtest_app, name="backtest")

console = Console()
err_console = Console(stderr=True, style="red")

DEFAULT_CONFIG = "configs/alarms.example.yaml"
DEFAULT_BACKTEST_CONFIG = "configs/backtest.example.yaml"


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# monitor commands
# ---------------------------------------------------------------------------

@monitor_app.command("start")
def monitor_start(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Alarms YAML config"),
    interval: int = typer.Option(60, "--interval", "-i", help="Poll interval in seconds"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start the polling daemon (blocking)."""
    _setup_logging(verbose)
    from market_tracker.monitor.daemon import MonitorDaemon

    daemon = MonitorDaemon(config_path=config, interval_seconds=interval)
    daemon.start()


@monitor_app.command("status")
def monitor_status(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Show active alarms and current dedup state."""
    from market_tracker.alarms.state import AlarmStateManager
    from market_tracker.config import load_alarms_config

    try:
        cfg = load_alarms_config(config)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"Error: {exc}")
        raise typer.Exit(1)

    state_mgr = AlarmStateManager()
    states = state_mgr.get_all_states()
    now = datetime.now(tz=timezone.utc)

    table = Table(title=f"Alarm Status — {config}")
    table.add_column("Alarm", style="cyan")
    table.add_column("Cooldown", style="yellow")
    table.add_column("Last Fired")
    table.add_column("Silenced Until", style="magenta")
    table.add_column("Status", style="bold")

    for alarm in cfg.alarms:
        st = states.get(alarm.name)
        last_fired = st.last_fired.strftime("%Y-%m-%d %H:%M UTC") if st and st.last_fired else "—"
        silenced = (
            st.silenced_until.strftime("%Y-%m-%d %H:%M UTC")
            if st and st.silenced_until and now < st.silenced_until
            else "—"
        )
        suppressed = state_mgr.is_suppressed(alarm.name, alarm.cooldown_minutes)
        status = "[red]SUPPRESSED[/red]" if suppressed else "[green]ACTIVE[/green]"
        table.add_row(alarm.name, f"{alarm.cooldown_minutes}m", last_fired, silenced, status)

    console.print(table)


# ---------------------------------------------------------------------------
# alarm commands
# ---------------------------------------------------------------------------

@alarm_app.command("list")
def alarm_list(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Pretty-print all loaded alarm rules."""
    from market_tracker.config import load_alarms_config

    try:
        cfg = load_alarms_config(config)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"Error: {exc}")
        raise typer.Exit(1)

    for alarm in cfg.alarms:
        console.rule(f"[bold cyan]{alarm.name}[/bold cyan]")
        console.print(f"  Logic: [yellow]{alarm.logic}[/yellow]  Cooldown: {alarm.cooldown_minutes}m")
        for rule in alarm.rules:
            console.print(f"  • [{rule.type}] {rule.symbol}  {rule.params}")


@alarm_app.command("test")
def alarm_test(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    send_alert: bool = typer.Option(False, "--send-alert", help="Actually send SNS SMS"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """One-shot dry-run evaluation against live market data."""
    _setup_logging(verbose)
    from market_tracker.alarms.evaluator import evaluate_alarm
    from market_tracker.config import load_alarms_config

    try:
        cfg = load_alarms_config(config)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"Error: {exc}")
        raise typer.Exit(1)

    table = Table(title="Alarm Test Results")
    table.add_column("Alarm", style="cyan")
    table.add_column("Triggered", style="bold")
    table.add_column("Details")

    for alarm in cfg.alarms:
        result = evaluate_alarm(alarm)
        triggered_str = "[red]YES[/red]" if result.triggered else "[green]NO[/green]"
        details = " | ".join(result.messages[:2])
        table.add_row(alarm.name, triggered_str, details)

        if result.triggered and send_alert:
            from market_tracker.alerts.sns import send_sms
            msg = f"[TEST] {alarm.name} TRIGGERED: {'; '.join(result.messages[:2])}"
            ok = send_sms(msg)
            console.print(f"  SNS send: {'OK' if ok else 'FAILED'}")

    console.print(table)


@alarm_app.command("silence")
def alarm_silence(
    name: str = typer.Argument(..., help="Alarm name to silence"),
    hours: float = typer.Option(4.0, "--hours", "-h", help="Hours to silence"),
) -> None:
    """Silence an alarm for N hours."""
    from market_tracker.alarms.state import AlarmStateManager

    state_mgr = AlarmStateManager()
    until = state_mgr.silence(name, hours)
    console.print(
        f"Alarm '[cyan]{name}[/cyan]' silenced until "
        f"[yellow]{until.strftime('%Y-%m-%d %H:%M UTC')}[/yellow]"
    )


# ---------------------------------------------------------------------------
# backtest commands
# ---------------------------------------------------------------------------

@backtest_app.command("run")
def backtest_run(
    config: str = typer.Option(DEFAULT_BACKTEST_CONFIG, "--config", "-c"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save result JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run a backtest and print performance metrics."""
    _setup_logging(verbose)
    from market_tracker.backtest.engine import run_backtest
    from market_tracker.config import load_backtest_config

    try:
        cfg = load_backtest_config(config)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"Error: {exc}")
        raise typer.Exit(1)

    console.print(f"Running backtest for [cyan]{cfg.backtest.symbol}[/cyan]…")
    result = run_backtest(cfg.backtest)
    _print_backtest_result(result)

    if output:
        Path(output).write_text(result.model_dump_json(indent=2))
        console.print(f"Result saved to [green]{output}[/green]")


@backtest_app.command("report")
def backtest_report(
    file: str = typer.Argument(..., help="Path to saved backtest result JSON"),
) -> None:
    """Load a saved backtest result and render the metrics table."""
    from market_tracker.models import BacktestResult

    try:
        raw = Path(file).read_text()
        result = BacktestResult.model_validate_json(raw)
    except Exception as exc:
        err_console.print(f"Error loading {file}: {exc}")
        raise typer.Exit(1)

    _print_backtest_result(result)


def _print_backtest_result(result) -> None:
    """Render a BacktestResult as a Rich table."""
    table = Table(title=f"Backtest — {result.symbol} ({result.start_date} → {result.end_date})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")

    rows = [
        ("Initial Capital", f"${result.initial_capital:,.2f}"),
        ("Final Capital", f"${result.final_capital:,.2f}"),
        ("Total Return", f"{result.total_return_pct:+.2f}%"),
        ("Max Drawdown", f"{result.max_drawdown_pct:.2f}%"),
        ("Longest Drawdown", f"{result.longest_drawdown_days} days"),
        ("Sharpe Ratio", f"{result.sharpe_ratio:.3f}"),
        ("Win Rate", f"{result.win_rate_pct:.1f}%"),
        ("Profit Factor", f"{result.profit_factor:.2f}"),
        ("Avg Win", f"{result.avg_win_pct:+.2f}%"),
        ("Avg Loss", f"{result.avg_loss_pct:+.2f}%"),
        ("Total Trades", str(result.total_trades)),
        ("Winning Trades", str(result.winning_trades)),
        ("Losing Trades", str(result.losing_trades)),
    ]
    for metric, value in rows:
        table.add_row(metric, value)

    console.print(table)

    if result.trades:
        trade_table = Table(title="Trade Log", show_lines=True)
        for col in ["Entry Date", "Exit Date", "Entry $", "Exit $", "Shares", "P&L", "Exit Reason"]:
            trade_table.add_column(col)

        for t in result.trades[-20:]:  # show last 20
            pnl_style = "green" if t.pnl >= 0 else "red"
            trade_table.add_row(
                t.entry_date,
                t.exit_date,
                f"{t.entry_price:.2f}",
                f"{t.exit_price:.2f}",
                str(t.shares),
                f"[{pnl_style}]{t.pnl:+.2f} ({t.pnl_pct:+.2f}%)[/{pnl_style}]",
                t.exit_reason,
            )
        console.print(trade_table)


if __name__ == "__main__":
    app()
