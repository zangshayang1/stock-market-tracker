"""
QQQ Dip Accumulation Backtest
------------------------------
Strategy: Buy $100 of QQQ on every day the close drops >= 2% from the
          previous close. Never sell. Hold all shares until today.

Runs from QQQ inception (1999-03-10) through today.
"""
from __future__ import annotations

import sys
from datetime import date, datetime

import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table

console = Console()

SYMBOL         = "QQQ"
DOLLARS_PER_DIP = 100.0
THRESHOLD_PCT   = 2.0          # drop >= 2% triggers a buy
INCEPTION_DATE  = "1999-03-10"
TODAY           = date.today().isoformat()


def run() -> None:
    console.print(f"Fetching [cyan]{SYMBOL}[/cyan] from {INCEPTION_DATE} → {TODAY}…")

    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period="max", interval="1d", auto_adjust=True)

    if df.empty:
        console.print("[red]Error: no data returned from yfinance[/red]")
        sys.exit(1)

    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[df.index >= INCEPTION_DATE].copy()
    df = df[df["Close"].notna() & (df["Close"] > 0)]

    # Daily % change from previous close
    df["prev_close"] = df["Close"].shift(1)
    df["change_pct"] = (df["Close"] - df["prev_close"]) / df["prev_close"] * 100

    # Drop the first row (no prev_close)
    df = df.iloc[1:].copy()

    # Identify dip days
    dip_mask = df["change_pct"] <= -THRESHOLD_PCT
    dip_days = df[dip_mask].copy()

    # Accumulate shares: $100 / close price on each dip day
    dip_days["shares_bought"] = DOLLARS_PER_DIP / dip_days["Close"]

    total_shares = dip_days["shares_bought"].sum()
    total_invested = len(dip_days) * DOLLARS_PER_DIP
    final_price = float(df["Close"].iloc[-1])
    final_date = df.index[-1].date()
    current_value = total_shares * final_price
    total_return_pct = (current_value - total_invested) / total_invested * 100

    # Annualized CAGR from first purchase to today
    first_buy_date = dip_days.index[0].date()
    years = (final_date - first_buy_date).days / 365.25
    cagr = ((current_value / total_invested) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    # Worst single dip day
    worst_day = df["change_pct"].idxmin()
    worst_pct = df.loc[worst_day, "change_pct"]

    # Dip frequency
    total_trading_days = len(df)
    dip_frequency_pct = len(dip_days) / total_trading_days * 100

    # -----------------------------------------------------------------------
    # Buy-and-hold benchmark: invest $100 on day 1 only
    # -----------------------------------------------------------------------
    first_close = float(df["Close"].iloc[0])
    bnh_shares = DOLLARS_PER_DIP / first_close
    bnh_value = bnh_shares * final_price
    bnh_return_pct = (bnh_value - DOLLARS_PER_DIP) / DOLLARS_PER_DIP * 100
    bnh_years = (final_date - df.index[0].date()).days / 365.25
    bnh_cagr = ((bnh_value / DOLLARS_PER_DIP) ** (1 / bnh_years) - 1) * 100

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    summary = Table(title=f"QQQ Dip Accumulation  |  {INCEPTION_DATE} → {TODAY}")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="bold")

    summary.add_row("Strategy", f"Buy ${DOLLARS_PER_DIP:.0f} on any day QQQ drops ≥{THRESHOLD_PCT}%")
    summary.add_row("Period", f"{INCEPTION_DATE} → {final_date}")
    summary.add_row("Total trading days", f"{total_trading_days:,}")
    summary.add_row("Dip days (≥2% drop)", f"{len(dip_days):,}  ({dip_frequency_pct:.1f}% of trading days)")
    summary.add_row("Total invested", f"${total_invested:,.0f}")
    summary.add_row("Total shares accumulated", f"{total_shares:.4f}")
    summary.add_row("Final QQQ price", f"${final_price:,.2f}  ({final_date})")
    summary.add_row("Portfolio value today", f"${current_value:,.2f}")
    summary.add_row("Total return", f"[green]+{total_return_pct:.1f}%[/green]" if total_return_pct >= 0 else f"[red]{total_return_pct:.1f}%[/red]")
    summary.add_row("Annualized CAGR", f"{cagr:.2f}%  (from first buy {first_buy_date})")
    summary.add_row("Worst single dip day", f"{worst_day.date()}  ({worst_pct:.1f}%)")

    console.print(summary)

    # Benchmark comparison
    bench = Table(title="Benchmark: $100 Buy-and-Hold from Day 1")
    bench.add_column("Metric", style="cyan")
    bench.add_column("Dip Strategy", style="bold yellow")
    bench.add_column("Buy & Hold $100", style="bold blue")

    bench.add_row("Total invested",   f"${total_invested:,.0f}",   f"${DOLLARS_PER_DIP:.0f}")
    bench.add_row("Portfolio value",  f"${current_value:,.2f}",    f"${bnh_value:,.2f}")
    bench.add_row("Total return",     f"{total_return_pct:.1f}%",  f"{bnh_return_pct:.1f}%")
    bench.add_row("CAGR",             f"{cagr:.2f}%",              f"{bnh_cagr:.2f}%")
    bench.add_row("Gain (absolute)",  f"${current_value - total_invested:,.2f}", f"${bnh_value - DOLLARS_PER_DIP:.2f}")

    console.print(bench)

    # Top 10 largest dip buys
    top_dips = dip_days.nsmallest(10, "change_pct")[["Close", "change_pct", "shares_bought"]].copy()
    top_dips["cost"] = DOLLARS_PER_DIP

    dip_table = Table(title="10 Largest Single-Day Drops (biggest buys)")
    dip_table.add_column("Date")
    dip_table.add_column("Close", justify="right")
    dip_table.add_column("Day Change", justify="right", style="red")
    dip_table.add_column("Shares Bought", justify="right")
    dip_table.add_column("Value Today", justify="right", style="green")

    for idx, row in top_dips.iterrows():
        shares = row["shares_bought"]
        dip_table.add_row(
            str(idx.date()),
            f"${row['Close']:.2f}",
            f"{row['change_pct']:.2f}%",
            f"{shares:.4f}",
            f"${shares * final_price:,.2f}",
        )

    console.print(dip_table)


if __name__ == "__main__":
    run()
