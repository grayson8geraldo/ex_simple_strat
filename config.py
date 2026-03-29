"""
Fibonacci Continuation Model (FCM) — Configuration
Paper trading system for index ETFs.
"""

# ── Symbols & Data ──────────────────────────────────────────────
SYMBOLS = ["SPY", "QQQ", "DIA"]          # Index proxy ETFs
TIMEFRAME = "1h"                          # yfinance interval
LOOKBACK_PERIOD = "30d"                   # History depth

# ── Paper Account ───────────────────────────────────────────────
INITIAL_BALANCE = 2000.0                  # USD
RISK_PER_TRADE_PCT = 1.0                  # Max % of balance risked per trade
MAX_OPEN_POSITIONS = 2                    # Concurrent position limit
FRACTIONAL_SHARES = True                  # Allow fractional sizing

# ── Fibonacci Levels ────────────────────────────────────────────
FIB_LEVELS = [0.0, 0.5, 0.618, 1.0, 1.5]
RETRACEMENT_ZONE_LOW = 0.5               # 50%
RETRACEMENT_ZONE_HIGH = 0.618            # 61.8%

# ── Impulse Detection ──────────────────────────────────────────
SWING_ORDER = 3                           # Fractal order (bars each side)
IMPULSE_MIN_BARS = 5                      # Minimum candles for valid impulse
IMPULSE_MIN_ATR_MULTIPLE = 2.0            # Impulse must span >= N × ATR
IMPULSE_MAX_RETRACE_RATIO = 0.382         # Max intermediate retrace within impulse

# ── Indicators ──────────────────────────────────────────────────
ATR_PERIOD = 14
EMA_PERIOD = 21

# ── Risk Management ────────────────────────────────────────────
SL_ATR_BUFFER = 0.5                       # ATR multiplier added beyond Fib level for SL

# ── Polling ─────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 300               # 5 minutes between cycles
