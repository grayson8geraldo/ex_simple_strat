"""
Fibonacci Continuation Model (FCM) with TFC entry pattern.

Pipeline:
  1. Detect swing highs/lows (fractals)
  2. Identify impulse moves
  3. Compute Fibonacci retracement levels
  4. Wait for price to retrace into 0.5–0.618 zone
  5. Detect TFC confirmation candle (price action trigger)
  6. Emit Signal with entry, SL, TP
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from config import (
    ATR_PERIOD,
    EMA_PERIOD,
    FIB_LEVELS,
    IMPULSE_MAX_RETRACE_RATIO,
    IMPULSE_MIN_ATR_MULTIPLE,
    IMPULSE_MIN_BARS,
    MIN_RISK_REWARD,
    RETRACEMENT_ZONE_HIGH,
    RETRACEMENT_ZONE_LOW,
    SL_ATR_BUFFER,
    SWING_ORDER,
)

log = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────

@dataclass
class FibLevels:
    start_price: float        # Level 1 (impulse origin)
    end_price: float          # Level 0 (impulse endpoint)
    start_idx: int            # Bar index of impulse start
    end_idx: int              # Bar index of impulse end
    direction: str            # "bullish" or "bearish"
    levels: dict[float, float] = field(default_factory=dict)

    def __post_init__(self):
        move = abs(self.end_price - self.start_price)
        if self.direction == "bullish":
            # Impulse went UP: level 0 = top, level 1 = bottom
            for ratio in FIB_LEVELS:
                self.levels[ratio] = self.end_price - ratio * move
            # Extension: 1.5 means price continues UP beyond impulse end
            self.levels[1.5] = self.end_price + 0.5 * move
        else:
            # Impulse went DOWN: level 0 = bottom, level 1 = top
            for ratio in FIB_LEVELS:
                self.levels[ratio] = self.end_price + ratio * move
            # Extension: price continues DOWN
            self.levels[1.5] = self.end_price - 0.5 * move


@dataclass
class Signal:
    symbol: str
    direction: str            # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profit_1: float      # Fib level 0
    take_profit_2: float      # Fib level 1.5
    signal_time: datetime
    signal_candle_idx: int
    fib: FibLevels
    pending: bool = False     # True if confirmation candle not yet closed

    @property
    def risk_reward(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit_1 - self.entry_price)
        return reward / risk if risk > 0 else 0.0


# ── Stage 1: Swing detection ───────────────────────────────────

def find_swing_points(df: pd.DataFrame, order: int = SWING_ORDER) -> pd.DataFrame:
    """Mark swing highs and swing lows using Williams fractal method."""
    n = len(df)
    swing_high = np.zeros(n, dtype=bool)
    swing_low = np.zeros(n, dtype=bool)
    highs = df["high"].values
    lows = df["low"].values

    for i in range(order, n - order):
        # Swing high: highest high in window
        if highs[i] == np.max(highs[i - order: i + order + 1]):
            swing_high[i] = True
        # Swing low: lowest low in window
        if lows[i] == np.min(lows[i - order: i + order + 1]):
            swing_low[i] = True

    df["swing_high"] = swing_high
    df["swing_low"] = swing_low
    return df


# ── Stage 2: Impulse detection ─────────────────────────────────

def detect_impulses(df: pd.DataFrame) -> list[FibLevels]:
    """Find valid impulse moves from swing point pairs."""
    atr_col = f"atr_{ATR_PERIOD}"
    if atr_col not in df.columns:
        return []

    sh_indices = np.where(df["swing_high"].values)[0]
    sl_indices = np.where(df["swing_low"].values)[0]

    # Merge and sort all swing points chronologically
    swings = []
    for idx in sh_indices:
        swings.append((idx, "high", df["high"].iat[idx]))
    for idx in sl_indices:
        swings.append((idx, "low", df["low"].iat[idx]))
    swings.sort(key=lambda x: x[0])

    if len(swings) < 2:
        return []

    impulses = []
    highs = df["high"].values
    lows = df["low"].values
    atr_vals = df[atr_col].values

    for i in range(len(swings) - 1):
        s_idx, s_type, s_price = swings[i]
        e_idx, e_type, e_price = swings[i + 1]

        # Must be opposite types
        if s_type == e_type:
            continue

        bar_span = e_idx - s_idx
        if bar_span < IMPULSE_MIN_BARS:
            continue

        move = abs(e_price - s_price)
        atr_at_start = atr_vals[s_idx]
        if atr_at_start <= 0 or move < IMPULSE_MIN_ATR_MULTIPLE * atr_at_start:
            continue

        # Determine direction
        if s_type == "low" and e_type == "high":
            direction = "bullish"
            # Check intermediate retracement
            segment_lows = lows[s_idx:e_idx + 1]
            max_retrace = s_price - np.min(segment_lows) if np.min(segment_lows) < s_price else 0
        else:
            direction = "bearish"
            segment_highs = highs[s_idx:e_idx + 1]
            max_retrace = np.max(segment_highs) - s_price if np.max(segment_highs) > s_price else 0

        if move > 0 and max_retrace / move > IMPULSE_MAX_RETRACE_RATIO:
            continue

        impulses.append(FibLevels(
            start_price=s_price,
            end_price=e_price,
            start_idx=s_idx,
            end_idx=e_idx,
            direction=direction,
        ))

    return impulses


# ── Stage 3: TFC entry detection ───────────────────────────────

def _candle_touches_zone(bar_high: float, bar_low: float,
                         zone_low: float, zone_high: float) -> bool:
    """Check if a candle's range overlaps the retracement zone."""
    return bar_low <= zone_high and bar_high >= zone_low


def detect_tfc_entry(df: pd.DataFrame, fib: FibLevels,
                     symbol: str) -> Signal | None:
    """Scan for TFC confirmation after an impulse."""
    n = len(df)
    start = fib.end_idx + 1
    if start >= n:
        return None

    ema_col = f"ema_{EMA_PERIOD}"
    atr_col = f"atr_{ATR_PERIOD}"

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    ema_vals = df[ema_col].values if ema_col in df.columns else None
    vwap_vals = df["vwap"].values if "vwap" in df.columns else None
    atr_vals = df[atr_col].values

    # Determine the retracement zone price bounds
    level_50 = fib.levels[RETRACEMENT_ZONE_LOW]
    level_618 = fib.levels[RETRACEMENT_ZONE_HIGH]
    zone_low = min(level_50, level_618)
    zone_high = max(level_50, level_618)

    signal_candle_idx = None

    for i in range(start, n):
        # Check if price has invalidated the setup (gone past level 1.0)
        level_1 = fib.levels[1.0]
        if fib.direction == "bullish" and lows[i] < level_1:
            return None
        if fib.direction == "bearish" and highs[i] > level_1:
            return None

        # Look for signal candle touching the zone
        if signal_candle_idx is None:
            if _candle_touches_zone(highs[i], lows[i], zone_low, zone_high):
                signal_candle_idx = i
            continue

        # We have a signal candle — check this candle for confirmation
        confirmed = False
        if fib.direction == "bullish":
            # Long: confirmation candle breaks above signal candle's high
            if highs[i] > highs[signal_candle_idx]:
                confirmed = True
        else:
            # Short: confirmation candle breaks below signal candle's low
            if lows[i] < lows[signal_candle_idx]:
                confirmed = True

        if not confirmed:
            # Move signal candle forward if this candle also touches zone
            if _candle_touches_zone(highs[i], lows[i], zone_low, zone_high):
                signal_candle_idx = i
            continue

        # ── Confluence filters ──────────────────────────────────
        # Price naturally dips below EMA during retrace, so we use
        # two softer checks:
        # 1) EMA must be trending with the impulse (compare to impulse start)
        # 2) Confirmation candle closes above signal candle (momentum shift)

        if ema_vals is not None:
            ema_at_impulse = ema_vals[fib.start_idx]
            ema_now = ema_vals[i]
            # EMA should have moved in impulse direction since start
            if fib.direction == "bullish" and ema_now < ema_at_impulse:
                signal_candle_idx = i if _candle_touches_zone(highs[i], lows[i], zone_low, zone_high) else None
                continue
            if fib.direction == "bearish" and ema_now > ema_at_impulse:
                signal_candle_idx = i if _candle_touches_zone(highs[i], lows[i], zone_low, zone_high) else None
                continue

        # Confirmation candle must close in the trend direction
        sc = signal_candle_idx
        if fib.direction == "bullish" and closes[i] < closes[sc]:
            signal_candle_idx = i if _candle_touches_zone(highs[i], lows[i], zone_low, zone_high) else None
            continue
        if fib.direction == "bearish" and closes[i] > closes[sc]:
            signal_candle_idx = i if _candle_touches_zone(highs[i], lows[i], zone_low, zone_high) else None
            continue

        # ── Build signal ────────────────────────────────────────
        atr_now = atr_vals[i] if i < len(atr_vals) else atr_vals[-1]
        pending = (i == n - 1)  # Last bar — not yet closed

        if fib.direction == "bullish":
            entry = highs[signal_candle_idx]
            sl = fib.levels[RETRACEMENT_ZONE_HIGH] - SL_ATR_BUFFER * atr_now
            tp1 = fib.levels[0.0]
            tp2 = fib.levels[1.5]
            direction = "long"
        else:
            entry = lows[signal_candle_idx]
            sl = fib.levels[RETRACEMENT_ZONE_HIGH] + SL_ATR_BUFFER * atr_now
            tp1 = fib.levels[0.0]
            tp2 = fib.levels[1.5]
            direction = "short"

        return Signal(
            symbol=symbol,
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            signal_time=df.index[i],
            signal_candle_idx=signal_candle_idx,
            fib=fib,
            pending=pending,
        )

    return None


# ── Top-level scanner ──────────────────────────────────────────

def scan_for_signals(df: pd.DataFrame, symbol: str) -> list[Signal]:
    """Full pipeline: find impulses → detect TFC entries → return signals."""
    df = find_swing_points(df)
    impulses = detect_impulses(df)

    if not impulses:
        return []

    # Keep only the 3 most recent impulses
    impulses = impulses[-3:]

    signals = []
    seen_bars = set()

    for imp in impulses:
        sig = detect_tfc_entry(df, imp, symbol)
        if sig is not None and sig.signal_candle_idx not in seen_bars:
            if sig.risk_reward >= MIN_RISK_REWARD:
                signals.append(sig)
                seen_bars.add(sig.signal_candle_idx)

    # Sort by risk:reward descending
    signals.sort(key=lambda s: s.risk_reward, reverse=True)
    return signals
