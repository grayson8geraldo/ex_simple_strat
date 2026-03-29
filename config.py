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
RISK_PER_TRADE_PCT = 3.0                  # Aggressive: 3% of balance per trade
MAX_OPEN_POSITIONS = 3                    # Allow 3 concurrent positions
FRACTIONAL_SHARES = True                  # Allow fractional sizing

# ── Compounding / Acceleration ──────────────────────────────────
# Scale risk up as account grows (Kelly-lite approach)
COMPOUND_ENABLED = True                   # Reinvest profits into sizing
RISK_SCALE_TIERS = [                      # (equity_multiple, risk_pct)
    (1.0, 3.0),                           # $200+  → 3% risk
    (1.5, 4.0),                           # $300+  → 4% risk
    (2.0, 5.0),                           # $400+  → 5% risk
    (3.0, 4.0),                           # $600+  → back to 4% (protect gains)
    (5.0, 3.0),                           # $1000+ → back to 3%
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
