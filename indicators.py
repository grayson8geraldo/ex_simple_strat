"""
Technical indicators: EMA, VWAP, ATR.
"""

import numpy as np
import pandas as pd

from config import ATR_PERIOD, EMA_PERIOD


def compute_ema(df: pd.DataFrame, period: int = EMA_PERIOD) -> pd.DataFrame:
    """Add EMA column."""
    df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()
    return df


def compute_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP column (resets daily)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol = tp * df["volume"]

    dates = df.index.date
    cum_tp_vol = tp_vol.groupby(dates).cumsum()
    cum_vol = df["volume"].groupby(dates).cumsum()

    df["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)
    df["vwap"] = df["vwap"].ffill()
    return df


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
    """Add ATR column using Wilder smoothing."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    df[f"atr_{period}"] = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all indicators to the DataFrame."""
    df = compute_atr(df)
    df = compute_ema(df)
    df = compute_vwap(df)
    return df
