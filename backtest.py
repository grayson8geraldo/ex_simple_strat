#!/usr/bin/env python3
"""
Backtest module — run the FCM strategy over historical data.

Can load data from CSV files or use yfinance (when network is available).
CSV format: date,open,high,low,close,volume (header required).

Usage:
    python backtest.py                          # yfinance data
    python backtest.py --csv data/SPY_1h.csv    # from CSV file
    python backtest.py --symbol SPY --period 60d --interval 1h
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime

import pandas as pd

import config
from indicators import enrich
from paper_trader import PaperTrader
from strategy import scan_for_signals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_csv(path: str) -> pd.DataFrame:
    """Load OHLCV data from CSV."""
    df = pd.read_csv(path, parse_dates=True, index_col=0)
    df.columns = [c.lower().strip() for c in df.columns]
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


def walk_forward(df: pd.DataFrame, symbol: str, trader: PaperTrader,
                 warmup: int = 50, step: int = 1) -> None:
    """Walk-forward backtest: expand the window bar by bar."""
    n = len(df)
    if n < warmup:
        log.warning("Not enough bars for backtest (%d < %d warmup)", n, warmup)
        return

    last_signal_bar = -1

    for end in range(warmup, n, step):
        window = df.iloc[:end + 1].copy()
        window = enrich(window)

        # Update positions with latest bar
        last = window.iloc[-1]
        current_bars = {symbol: {
            "high": last["high"],
            "low": last["low"],
            "close": last["close"],
            "time": window.index[-1],
        }}
        trader.update_positions(current_bars)

        # Scan for new signals
        signals = scan_for_signals(window, symbol)
        for sig in signals:
            if sig.signal_candle_idx > last_signal_bar and not sig.pending:
                pos = trader.open_position(sig)
                if pos is not None:
                    last_signal_bar = sig.signal_candle_idx

    # Final status
    last = df.iloc[-1]
    trader.print_status({symbol: last["close"]})


def main() -> None:
    parser = argparse.ArgumentParser(description="FCM Backtest")
    parser.add_argument("--csv", type=str, help="Path to CSV file with OHLCV data")
    parser.add_argument("--symbol", default="SPY", help="Symbol name")
    parser.add_argument("--period", default="60d", help="yfinance lookback period")
    parser.add_argument("--interval", default="1h", help="yfinance interval")
    parser.add_argument("--balance", type=float, default=config.INITIAL_BALANCE,
                        help="Starting balance")
    args = parser.parse_args()

    print(f"\n  FCM Backtest — {args.symbol}")
    print(f"  Starting Balance: ${args.balance:,.2f}\n")

    if args.csv:
        df = load_csv(args.csv)
        print(f"  Loaded {len(df)} bars from {args.csv}")
    else:
        from data_feed import fetch_candles
        df = fetch_candles(args.symbol, args.interval, args.period)
        if df.empty:
            log.error("No data fetched. Use --csv to provide local data.")
            return
        print(f"  Fetched {len(df)} bars from yfinance")

    print(f"  Date range: {df.index[0]} — {df.index[-1]}\n")

    trader = PaperTrader(initial_balance=args.balance)
    walk_forward(df, args.symbol, trader)

    # Summary
    if trader.history:
        total_pnl = sum(t.pnl for t in trader.history)
        returns_pct = total_pnl / args.balance * 100
        print(f"  Return: {returns_pct:+.2f}%")
        print(f"  Final Equity: ${trader.balance:,.2f}")
    else:
        print("  No trades executed during backtest period.")


if __name__ == "__main__":
    main()
