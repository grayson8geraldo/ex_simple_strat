"""
Fibonacci Continuation Model (FCM) — Configuration
Paper trading system for index ETFs.
"""

# ── Symbols & Data ──────────────────────────────────────────────
SYMBOLS = ["SPY", "QQQ", "DIA"]          # Index proxy ETFs
TIMEFRAME = "1h"                          # yfinance interval
LOOKBACK_PERIOD = "30d"                   # History depth

# ── Paper Account ───────────────────────────────────────────────
INITIAL_BALANCE = 200.0                   # USD
MAX_OPEN_POSITIONS = 3                    # Allow 3 concurrent positions
FRACTIONAL_SHARES = True                  # Allow fractional sizing

# ── Compounding / Acceleration ──────────────────────────────────
# Процент = размер позиции от баланса (сколько денег вложено)
# Пример: баланс $200, тир 10% → позиция $20
COMPOUND_ENABLED = True
POSITION_SIZE_TIERS = [                   # (equity_multiple, position_pct)
    (1.0, 10.0),                          # $200+  → 10% ($20 позиция)
    (1.5, 8.0),                           # $300+  → 8%  ($24)
    (2.0, 6.0),                           # $400+  → 6%  ($24)
    (3.0, 4.0),                           # $600+  → 4%  ($24)
    (5.0, 3.0),                           # $1000+ → 3%  ($30)
]

# ── Fibonacci Levels ────────────────────────────────────────────
FIB_LEVELS = [0.0, 0.5, 0.618, 1.0, 1.5]
RETRACEMENT_ZONE_LOW = 0.5               # 50%
RETRACEMENT_ZONE_HIGH = 0.618            # 61.8%

# ── Impulse Detection ──────────────────────────────────────────
SWING_ORDER = 3                           # Fractal order (bars each side)
IMPULSE_MIN_BARS = 5                      # Minimum candles for valid impulse
IMPULSE_MIN_ATR_MULTIPLE = 1.5            # Lowered: catch more impulses
IMPULSE_MAX_RETRACE_RATIO = 0.382         # Max intermediate retrace within impulse

# ── Indicators ──────────────────────────────────────────────────
ATR_PERIOD = 14
EMA_PERIOD = 21

# ── Risk Management ────────────────────────────────────────────
SL_ATR_BUFFER = 0.3                       # Tighter SL → bigger position → faster growth
MIN_RISK_REWARD = 0.8                     # Accept 0.8:1+ R:R (aggressive)
TRAILING_STOP_ENABLED = True              # Trail SL after TP1 hit
TRAILING_STOP_ATR_MULT = 1.5             # Trailing distance in ATR units

# ── Polling ─────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 300               # 5 minutes between cycles
