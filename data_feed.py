"""
Market data fetching via yfinance.
"""

import logging
import yfinance as yf
import pandas as pd

log = logging.getLogger(__name__)


def fetch_candles(symbol: str, interval: str, period: str) -> pd.DataFrame:
    """Fetch OHLCV candles for a single symbol."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            log.warning("No data returned for %s", symbol)
            return pd.DataFrame()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        # Keep only OHLCV columns
        keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[keep].dropna()
        df["symbol"] = symbol
        return df
    except Exception as e:
        log.warning("Failed to fetch %s: %s", symbol, e)
        return pd.DataFrame()


def fetch_all(symbols: list[str], interval: str, period: str) -> dict[str, pd.DataFrame]:
    """Fetch candles for all symbols. Returns {symbol: DataFrame}."""
    result = {}
    for sym in symbols:
        df = fetch_candles(sym, interval, period)
        if not df.empty:
            result[sym] = df
    return result
