#!/usr/bin/env python3
"""
Fibonacci Continuation Model (FCM) — Paper Trading System

Trades index ETFs (SPY, QQQ, DIA) using Fibonacci retracement
with TFC price-action confirmation. Paper balance: $2,000.

Usage:
    python main.py                  # Run with defaults
    python main.py --once           # Single scan, no loop
    python main.py --symbols SPY    # Override symbols
    python main.py --interval 1d    # Override timeframe
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime

import config
from data_feed import fetch_all
from indicators import enrich
from paper_trader import PaperTrader
from strategy import scan_for_signals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def print_banner(symbols: list[str], interval: str, period: str) -> None:
    print(r"""
    ╔══════════════════════════════════════════════════════════╗
    ║   Fibonacci Continuation Model (FCM) — Paper Trader     ║
    ║   Strategy: TFC (Trend Following Continuation)          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    print(f"  Symbols:    {', '.join(symbols)}")
    print(f"  Timeframe:  {interval}")
    print(f"  Lookback:   {period}")
    print(f"  Balance:    ${config.INITIAL_BALANCE:,.2f}")
    print(f"  Risk/Trade: {config.RISK_PER_TRADE_PCT}% (scales with equity)")
    print(f"  Max Positions: {config.MAX_OPEN_POSITIONS}")
    print(f"  Compounding: {'ON' if config.COMPOUND_ENABLED else 'OFF'}")
    print(f"  Fib Levels: {config.FIB_LEVELS}")
    print(f"  Entry Zone: {config.RETRACEMENT_ZONE_LOW}–{config.RETRACEMENT_ZONE_HIGH}")
    print()


def run_cycle(trader: PaperTrader, symbols: list[str],
              interval: str, period: str) -> None:
    """One full scan cycle: fetch data → enrich → detect signals → trade."""
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] Scanning {', '.join(symbols)} ({interval})...")

    data = fetch_all(symbols, interval, period)
    if not data:
        log.warning("No data received — skipping cycle")
        return

    current_bars: dict[str, dict] = {}
    current_prices: dict[str, float] = {}
    all_signals = []

    for sym, df in data.items():
        if df.empty or len(df) < 30:
            log.info("Insufficient data for %s (%d bars)", sym, len(df))
            continue

        df = enrich(df)

        # Build latest bar info
        last = df.iloc[-1]
        atr_col = f"atr_{config.ATR_PERIOD}"
        current_bars[sym] = {
            "high": last["high"],
            "low": last["low"],
            "close": last["close"],
            "time": df.index[-1],
            "atr": last[atr_col] if atr_col in df.columns else 0,
        }
        current_prices[sym] = last["close"]

        # Scan for signals
        signals = scan_for_signals(df, sym)
        if signals:
            log.info("Found %d signal(s) for %s", len(signals), sym)
            all_signals.extend(signals)
        else:
            log.info("No signals for %s", sym)

    # Update existing positions (SL/TP checks)
    trader.update_positions(current_bars)

    # Open new positions from signals
    for sig in all_signals:
        trader.open_position(sig)

    # Print portfolio status
    trader.print_status(current_prices)


def main() -> None:
    parser = argparse.ArgumentParser(description="FCM Paper Trader")
    parser.add_argument("--symbols", nargs="+", default=config.SYMBOLS,
                        help="Symbols to trade")
    parser.add_argument("--interval", default=config.TIMEFRAME,
                        help="Candle interval (e.g., 1h, 15m, 1d)")
    parser.add_argument("--period", default=config.LOOKBACK_PERIOD,
                        help="Lookback period (e.g., 30d, 60d)")
    parser.add_argument("--poll", type=int, default=config.POLL_INTERVAL_SECONDS,
                        help="Seconds between scan cycles")
    parser.add_argument("--once", action="store_true",
                        help="Run a single scan and exit")
    args = parser.parse_args()

    print_banner(args.symbols, args.interval, args.period)

    trader = PaperTrader()

    # Graceful shutdown
    def handle_exit(signum, frame):
        print("\n\nShutting down...")
        trader.print_status()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if args.once:
        run_cycle(trader, args.symbols, args.interval, args.period)
        return

    while True:
        try:
            run_cycle(trader, args.symbols, args.interval, args.period)
            log.info("Next scan in %d seconds...", args.poll)
            time.sleep(args.poll)
        except KeyboardInterrupt:
            handle_exit(None, None)
        except Exception as e:
            log.error("Cycle error: %s", e, exc_info=True)
            time.sleep(30)


if __name__ == "__main__":
    main()
