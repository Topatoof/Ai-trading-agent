"""
Risk Manager — Central gatekeeper. Every trade must pass all checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    """Result of a risk evaluation."""
    approved: bool
    reasons: List[str] = field(default_factory=list)
    modified_qty: Optional[int] = None      # If risk suggests reducing size
    risk_score: float = 0.0                 # 0 = safe, 1 = extreme risk

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reasons": self.reasons,
            "modified_qty": self.modified_qty,
            "risk_score": self.risk_score,
        }


class RiskManager:
    """
    Enforces all risk constraints on trade proposals.
    Every proposal must pass ALL checks to be approved.
    """

    def __init__(self):
        cfg = get_config().risk
        self._max_position_pct = cfg.max_position_pct
        self._max_concurrent = cfg.max_concurrent_positions
        self._min_confidence = cfg.min_confidence_threshold
        self._daily_dd_halt = cfg.daily_drawdown_halt_pct
        self._total_dd_halt = cfg.total_drawdown_halt_pct
        self._trailing_stop = cfg.trailing_stop_pct

        trading_cfg = get_config().trading
        self._max_trades_per_day = trading_cfg.max_trades_per_day
        self._min_interval = timedelta(minutes=trading_cfg.min_trade_interval_minutes)

        # Tracking state
        self._trades_today: List[dict] = []
        self._last_trade_time: Dict[str, datetime] = {}
        self._circuit_state = "NORMAL"  # NORMAL / CAUTION / HALTED

    @property
    def circuit_state(self) -> str:
        return self._circuit_state

    def set_circuit_state(self, state: str):
        """Manually set circuit breaker state (e.g., from dashboard reset)."""
        if state in ("NORMAL", "CAUTION", "HALTED"):
            old = self._circuit_state
            self._circuit_state = state
            logger.info("Circuit breaker: %s → %s", old, state)

    def reset_daily(self):
        """Reset daily counters (called at market open)."""
        self._trades_today = []
        logger.info("Daily risk counters reset")

    def evaluate(
        self,
        symbol: str,
        action: str,
        qty: int,
        estimated_value: float,
        confidence: float,
        portfolio_equity: float,
        cash_available: float,
        current_positions: Dict[str, float],   # symbol → market_value
        daily_pnl_pct: float,
        total_drawdown_pct: float,
    ) -> RiskDecision:
        """
        Evaluate a trade proposal against all risk constraints.

        Returns RiskDecision with approved=True only if ALL checks pass.
        """
        reasons: List[str] = []
        risk_score = 0.0

        # ── Check 1: Circuit breaker state ─────────────────────
        if self._circuit_state == "HALTED":
            return RiskDecision(
                approved=False,
                reasons=["Circuit breaker HALTED — no new trades allowed"],
                risk_score=1.0,
            )

        # ── Check 2: Daily trade count ─────────────────────────
        if len(self._trades_today) >= self._max_trades_per_day:
            reasons.append(
                f"Daily trade limit reached ({self._max_trades_per_day})"
            )

        # ── Check 3: Minimum interval for same symbol ─────────
        last_time = self._last_trade_time.get(symbol)
        if last_time and (datetime.utcnow() - last_time) < self._min_interval:
            remaining = self._min_interval - (datetime.utcnow() - last_time)
            reasons.append(
                f"Minimum interval not met for {symbol} "
                f"({remaining.seconds}s remaining)"
            )

        # ── Check 4: Confidence threshold ──────────────────────
        if confidence < self._min_confidence:
            reasons.append(
                f"Confidence {confidence:.2f} below threshold "
                f"{self._min_confidence:.2f}"
            )
            risk_score += 0.2

        # ── Check 5: Position size limit ───────────────────────
        if action == "BUY" and portfolio_equity > 0:
            existing_value = current_positions.get(symbol, 0.0)
            new_total = existing_value + estimated_value
            position_pct = new_total / portfolio_equity

            if position_pct > self._max_position_pct:
                max_allowed_value = (
                    self._max_position_pct * portfolio_equity - existing_value
                )
                reasons.append(
                    f"Position would be {position_pct:.1%} of portfolio "
                    f"(max {self._max_position_pct:.0%})"
                )
                risk_score += 0.3

        # ── Check 6: Concurrent positions limit ────────────────
        if (
            action == "BUY"
            and symbol not in current_positions
            and len(current_positions) >= self._max_concurrent
        ):
            reasons.append(
                f"Max concurrent positions reached ({self._max_concurrent})"
            )
            risk_score += 0.2

        # ── Check 7: Cash availability ─────────────────────────
        if action == "BUY" and estimated_value > cash_available:
            reasons.append(
                f"Insufficient cash: need ${estimated_value:.2f}, "
                f"have ${cash_available:.2f}"
            )
            risk_score += 0.5

        # ── Check 8: Daily drawdown ────────────────────────────
        if abs(daily_pnl_pct) > self._daily_dd_halt:
            reasons.append(
                f"Daily drawdown {daily_pnl_pct:.2%} exceeds limit "
                f"{self._daily_dd_halt:.0%}"
            )
            self._circuit_state = "HALTED"
            risk_score += 0.5
            logger.warning("CIRCUIT BREAKER: Daily drawdown halt triggered!")

        # ── Check 9: Total drawdown ────────────────────────────
        if total_drawdown_pct > self._total_dd_halt:
            reasons.append(
                f"Total drawdown {total_drawdown_pct:.2%} exceeds limit "
                f"{self._total_dd_halt:.0%}"
            )
            self._circuit_state = "HALTED"
            risk_score += 0.5
            logger.warning("CIRCUIT BREAKER: Total drawdown halt triggered!")

        # ── Check 10: Caution mode size reduction ──────────────
        modified_qty = None
        if self._circuit_state == "CAUTION" and action == "BUY":
            modified_qty = max(1, qty // 2)
            reasons.append(
                f"CAUTION mode: qty reduced from {qty} to {modified_qty}"
            )
            risk_score += 0.1

        # ── Final decision ─────────────────────────────────────
        # Filter to blocking reasons (those that should reject)
        blocking = [r for r in reasons if any(kw in r.lower() for kw in [
            "limit reached", "interval not met", "below threshold",
            "would be", "max concurrent", "insufficient cash",
            "drawdown", "halted",
        ])]

        approved = len(blocking) == 0
        risk_score = min(risk_score, 1.0)

        decision = RiskDecision(
            approved=approved,
            reasons=reasons,
            modified_qty=modified_qty,
            risk_score=risk_score,
        )

        if approved:
            logger.info("RISK APPROVED: %s %s (risk_score=%.2f)", action, symbol, risk_score)
        else:
            logger.warning(
                "RISK REJECTED: %s %s — %s",
                action, symbol, "; ".join(blocking),
            )

        return decision

    def record_trade(self, symbol: str):
        """Record that a trade was executed (for daily counting and interval tracking)."""
        self._trades_today.append({
            "symbol": symbol,
            "timestamp": datetime.utcnow(),
        })
        self._last_trade_time[symbol] = datetime.utcnow()
