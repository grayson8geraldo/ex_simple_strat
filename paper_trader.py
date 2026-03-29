"""
Paper trading engine — aggressive compounding for small accounts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from config import (
    COMPOUND_ENABLED,
    FRACTIONAL_SHARES,
    INITIAL_BALANCE,
    MAX_OPEN_POSITIONS,
    POSITION_SIZE_TIERS,
    TRAILING_STOP_ATR_MULT,
    TRAILING_STOP_ENABLED,
)
from strategy import Signal

log = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    direction: str          # "long" or "short"
    entry_price: float
    shares: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    entry_time: datetime
    status: str = "open"
    partial_tp_hit: bool = False
    original_shares: float = 0.0
    highest_since_tp1: float = 0.0   # For trailing stop (longs)
    lowest_since_tp1: float = 999999.0  # For trailing stop (shorts)

    def __post_init__(self):
        if self.original_shares == 0.0:
            self.original_shares = self.shares


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str


class PaperTrader:
    def __init__(self, initial_balance: float = INITIAL_BALANCE):
        self.initial_balance: float = initial_balance
        self.balance: float = initial_balance
        self.positions: list[Position] = []
        self.history: list[TradeRecord] = []
        self.peak_equity: float = initial_balance

    # ── Position sizing by equity tier ────────────────────────────

    def _current_position_pct(self) -> float:
        """Get current tier's position size as % of balance."""
        if not COMPOUND_ENABLED:
            return POSITION_SIZE_TIERS[0][1]
        equity = self._equity_estimate()
        multiple = equity / self.initial_balance
        pct = POSITION_SIZE_TIERS[0][1]
        for tier_mult, tier_pct in POSITION_SIZE_TIERS:
            if multiple >= tier_mult:
                pct = tier_pct
        return pct

    def _equity_estimate(self) -> float:
        """Quick equity estimate using entry prices (no live quote needed)."""
        held_value = sum(
            p.shares * p.entry_price
            for p in self.positions if p.status == "open" and p.shares > 0
        )
        return self.balance + held_value

    # ── Position sizing ─────────────────────────────────────────

    def _calc_shares(self, entry_price: float, stop_loss: float) -> float:
        pct = self._current_position_pct()
        # Размер позиции = процент от баланса
        position_budget = self.balance * pct / 100.0
        shares = position_budget / entry_price
        if not FRACTIONAL_SHARES:
            shares = int(shares)
        return round(shares, 6)

    # ── Opening positions ───────────────────────────────────────

    def open_position(self, sig: Signal) -> Position | None:
        if sig.pending:
            log.info("[PENDING] %s %s — awaiting confirmation candle",
                     sig.direction.upper(), sig.symbol)
            return None

        if len([p for p in self.positions if p.status == "open"]) >= MAX_OPEN_POSITIONS:
            log.info("[SKIP] Max open positions reached")
            return None

        for p in self.positions:
            if p.status == "open" and p.symbol == sig.symbol and p.direction == sig.direction:
                return None

        shares = self._calc_shares(sig.entry_price, sig.stop_loss)
        if shares <= 0:
            log.info("[SKIP] Position size too small for %s", sig.symbol)
            return None

        cost = shares * sig.entry_price
        if cost > self.balance:
            return None

        self.balance -= cost
        pos_pct = self._current_position_pct()

        pos = Position(
            symbol=sig.symbol,
            direction=sig.direction,
            entry_price=sig.entry_price,
            shares=shares,
            stop_loss=sig.stop_loss,
            take_profit_1=sig.take_profit_1,
            take_profit_2=sig.take_profit_2,
            entry_time=sig.signal_time,
        )
        self.positions.append(pos)

        print(f"\n{'='*60}")
        print(f"  NEW {sig.direction.upper()} — {sig.symbol}")
        print(f"  Entry: ${sig.entry_price:.2f}  |  Shares: {shares:.4f}  |  Cost: ${cost:.2f}")
        print(f"  SL: ${sig.stop_loss:.2f}  |  TP1: ${sig.take_profit_1:.2f}  |  TP2: ${sig.take_profit_2:.2f}")
        print(f"  R:R = 1:{sig.risk_reward:.2f}  |  Position: {pos_pct:.0f}% of balance")
        print(f"  Time: {sig.signal_time}")
        print(f"{'='*60}\n")
        return pos

    # ── Updating open positions ─────────────────────────────────

    def update_positions(self, current_bars: dict[str, dict]) -> None:
        """Check SL / TP / trailing stop against latest bar data.

        current_bars: {symbol: {"high", "low", "close", "time", "atr"(optional)}}
        """
        for pos in self.positions:
            if pos.status != "open" or pos.shares <= 0:
                continue
            bar = current_bars.get(pos.symbol)
            if bar is None:
                continue

            bar_high = bar["high"]
            bar_low = bar["low"]
            bar_time = bar["time"]
            bar_atr = bar.get("atr", 0)

            # ── Trailing stop update (after TP1) ────────────────
            if pos.partial_tp_hit and TRAILING_STOP_ENABLED and bar_atr > 0:
                if pos.direction == "long":
                    if bar_high > pos.highest_since_tp1:
                        pos.highest_since_tp1 = bar_high
                    new_trail = pos.highest_since_tp1 - TRAILING_STOP_ATR_MULT * bar_atr
                    if new_trail > pos.stop_loss:
                        pos.stop_loss = new_trail
                else:
                    if bar_low < pos.lowest_since_tp1:
                        pos.lowest_since_tp1 = bar_low
                    new_trail = pos.lowest_since_tp1 + TRAILING_STOP_ATR_MULT * bar_atr
                    if new_trail < pos.stop_loss:
                        pos.stop_loss = new_trail

            # ── Stop loss ───────────────────────────────────────
            sl_hit = False
            if pos.direction == "long" and bar_low <= pos.stop_loss:
                sl_hit = True
            elif pos.direction == "short" and bar_high >= pos.stop_loss:
                sl_hit = True

            if sl_hit:
                self._close_position(pos, pos.stop_loss, bar_time, "stop_loss")
                continue

            # ── Take profit 1 (partial close) ──────────────────
            if not pos.partial_tp_hit:
                tp1_hit = False
                if pos.direction == "long" and bar_high >= pos.take_profit_1:
                    tp1_hit = True
                elif pos.direction == "short" and bar_low <= pos.take_profit_1:
                    tp1_hit = True

                if tp1_hit:
                    self._partial_close(pos, pos.take_profit_1, bar_time)
                    # Initialize trailing stop tracking
                    if pos.direction == "long":
                        pos.highest_since_tp1 = bar_high
                    else:
                        pos.lowest_since_tp1 = bar_low
                    continue

            # ── Take profit 2 (full close) ─────────────────────
            if pos.partial_tp_hit:
                tp2_hit = False
                if pos.direction == "long" and bar_high >= pos.take_profit_2:
                    tp2_hit = True
                elif pos.direction == "short" and bar_low <= pos.take_profit_2:
                    tp2_hit = True

                if tp2_hit:
                    self._close_position(pos, pos.take_profit_2, bar_time, "take_profit_2")

    def _calc_pnl(self, direction: str, entry: float, exit_price: float, shares: float) -> float:
        if direction == "long":
            return (exit_price - entry) * shares
        else:
            return (entry - exit_price) * shares

    def _partial_close(self, pos: Position, price: float, time: datetime) -> None:
        close_shares = pos.shares / 2.0
        pnl = self._calc_pnl(pos.direction, pos.entry_price, price, close_shares)

        returned = close_shares * pos.entry_price + pnl
        self.balance += returned

        pos.shares -= close_shares
        pos.partial_tp_hit = True
        pos.stop_loss = pos.entry_price  # Move SL to breakeven

        self.history.append(TradeRecord(
            symbol=pos.symbol, direction=pos.direction,
            entry_price=pos.entry_price, exit_price=price,
            shares=close_shares, pnl=pnl,
            entry_time=pos.entry_time, exit_time=time,
            exit_reason="take_profit_1",
        ))

        print(f"  [TP1 HIT] {pos.symbol} — closed {close_shares:.4f} @ ${price:.2f}"
              f"  P&L: ${pnl:+.2f}  |  SL → breakeven"
              f"  |  {'Trailing ON' if TRAILING_STOP_ENABLED else ''}")

    def _close_position(self, pos: Position, price: float,
                        time: datetime, reason: str) -> None:
        pnl = self._calc_pnl(pos.direction, pos.entry_price, price, pos.shares)
        returned = pos.shares * pos.entry_price + pnl
        self.balance += returned
        pos.status = "closed"

        self.history.append(TradeRecord(
            symbol=pos.symbol, direction=pos.direction,
            entry_price=pos.entry_price, exit_price=price,
            shares=pos.shares, pnl=pnl,
            entry_time=pos.entry_time, exit_time=time,
            exit_reason=reason,
        ))

        tag = {"stop_loss": "SL", "take_profit_2": "TP2", "trailing_stop": "TRAIL"}.get(reason, reason)
        print(f"  [{tag} HIT] {pos.symbol} — closed {pos.shares:.4f} @ ${price:.2f}"
              f"  P&L: ${pnl:+.2f}")
        pos.shares = 0.0

    # ── Reporting ───────────────────────────────────────────────

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        total = 0.0
        for pos in self.positions:
            if pos.status != "open" or pos.shares <= 0:
                continue
            price = current_prices.get(pos.symbol, pos.entry_price)
            total += self._calc_pnl(pos.direction, pos.entry_price, price, pos.shares)
        return total

    def print_status(self, current_prices: dict[str, float] | None = None) -> None:
        if current_prices is None:
            current_prices = {}

        open_positions = [p for p in self.positions if p.status == "open" and p.shares > 0]
        u_pnl = self.unrealized_pnl(current_prices)
        equity = self.balance + u_pnl
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (self.peak_equity - equity) / self.peak_equity * 100 if self.peak_equity > 0 else 0
        growth = (equity - self.initial_balance) / self.initial_balance * 100
        pos_pct = self._current_position_pct()

        print(f"\n{'─'*60}")
        print(f"  PORTFOLIO STATUS")
        print(f"  Cash: ${self.balance:,.2f}  |  Equity: ${equity:,.2f}")
        print(f"  Growth: {growth:+.1f}%  |  Drawdown: {drawdown:.1f}%")
        print(f"  Position Size: {pos_pct:.0f}% of balance per trade")
        print(f"  Open Positions: {len(open_positions)}")

        for p in open_positions:
            price = current_prices.get(p.symbol, p.entry_price)
            pnl = self._calc_pnl(p.direction, p.entry_price, price, p.shares)
            trail_info = f" SL=${p.stop_loss:.2f}" if p.partial_tp_hit else ""
            print(f"    {p.direction.upper()} {p.symbol}: "
                  f"{p.shares:.4f} @ ${p.entry_price:.2f} "
                  f"→ ${price:.2f}  P&L: ${pnl:+.2f}"
                  f"{' [TP1+trail]' if p.partial_tp_hit else ''}{trail_info}")

        if self.history:
            wins = [t for t in self.history if t.pnl > 0]
            losses = [t for t in self.history if t.pnl <= 0]
            total_pnl = sum(t.pnl for t in self.history)
            win_rate = len(wins) / len(self.history) * 100
            gross_profit = sum(t.pnl for t in wins) if wins else 0
            gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
            pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

            print(f"\n  STATS: {len(self.history)} trades  |  WR: {win_rate:.0f}%"
                  f"  |  PF: {pf:.2f}  |  P&L: ${total_pnl:+,.2f}")
            if wins:
                print(f"  Best: ${max(t.pnl for t in wins):+,.2f}", end="")
            if losses:
                print(f"  |  Worst: ${min(t.pnl for t in losses):+,.2f}", end="")
            print()

        print(f"{'─'*60}\n")
