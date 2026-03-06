"""
QQQ: Dip Buying vs Periodic DCA
---------------------------------
Compares two strategies with identical total capital deployed:
  A) Dip strategy  — buy $100 on every day QQQ drops >= 2% (595 buys)
  B) Periodic DCA  — buy $100 every Nth trading day (same 595 buys, evenly spaced)

Both hold all shares until today. No selling.
"""
from __future__ import annotations

import sys
from datetime import date

import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table

console = Console()

SYMBOL          = "QQQ"
DOLLARS_PER_BUY = 100.0
THRESHOLD_PCT   = 2.0
INCEPTION_DATE  = "1999-03-10"


def run() -> None:
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period="max", interval="1d", auto_adjust=True)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[df.index >= INCEPTION_DATE].copy()
    df = df[df["Close"].notna() & (df["Close"] > 0)]

    df["prev_close"] = df["Close"].shift(1)
    df["change_pct"] = (df["Close"] - df["prev_close"]) / df["prev_close"] * 100
    df = df.iloc[1:].copy()

    final_price = float(df["Close"].iloc[-1])
    final_date  = df.index[-1].date()

    # ------------------------------------------------------------------
    # Strategy A: Dip buying
    # ------------------------------------------------------------------
    dip_days = df[df["change_pct"] <= -THRESHOLD_PCT].copy()
    n_buys = len(dip_days)
    dip_shares = (DOLLARS_PER_BUY / dip_days["Close"]).sum()
    total_invested = n_buys * DOLLARS_PER_BUY
    dip_value = dip_shares * final_price
    dip_return = (dip_value - total_invested) / total_invested * 100
    dip_years = (final_date - dip_days.index[0].date()).days / 365.25
    dip_cagr = ((dip_value / total_invested) ** (1 / dip_years) - 1) * 100

    # ------------------------------------------------------------------
    # Strategy B: Periodic DCA — every Nth trading day
    # ------------------------------------------------------------------
    # Space n_buys evenly across all trading days
    step = len(df) // n_buys
    periodic_idx = df.iloc[::step].iloc[:n_buys]  # take exactly n_buys rows
    periodic_shares = (DOLLARS_PER_BUY / periodic_idx["Close"]).sum()
    periodic_value = periodic_shares * final_price
    periodic_return = (periodic_value - total_invested) / total_invested * 100
    periodic_years = (final_date - periodic_idx.index[0].date()).days / 365.25
    periodic_cagr = ((periodic_value / total_invested) ** (1 / periodic_years) - 1) * 100
    period_days = step  # calendar trading days between each buy

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    table = Table(title=f"QQQ  |  {n_buys} buys × ${DOLLARS_PER_BUY:.0f}  |  Hold until {final_date}")
    table.add_column("Metric",           style="cyan")
    table.add_column("Dip Buying",       style="bold yellow",  justify="right")
    table.add_column(f"Periodic DCA\n(every ~{period_days} trading days)", style="bold blue", justify="right")

    table.add_row("Total invested",    f"${total_invested:,.0f}",   f"${total_invested:,.0f}")
    table.add_row("Shares accumulated",f"{dip_shares:.4f}",         f"{periodic_shares:.4f}")
    table.add_row("Portfolio value",   f"${dip_value:,.2f}",        f"${periodic_value:,.2f}")
    table.add_row("Total return",      f"{dip_return:.1f}%",        f"{periodic_return:.1f}%")
    table.add_row("CAGR",              f"{dip_cagr:.2f}%",          f"{periodic_cagr:.2f}%")
    table.add_row("Gain (absolute)",   f"${dip_value - total_invested:,.2f}", f"${periodic_value - total_invested:,.2f}")

    console.print(table)


if __name__ == "__main__":
    run()
