"""
Circuit Breaker — Monitors portfolio health and triggers emergency halts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.config import get_config

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    HALTED = "HALTED"


@dataclass
class CircuitBreakerStatus:
    """Current state of the circuit breaker."""
    state: CircuitState
    daily_pnl_pct: float
    total_drawdown_pct: float
    high_water_mark: float
    current_equity: float
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "daily_pnl_pct": round(self.daily_pnl_pct, 4),
            "total_drawdown_pct": round(self.total_drawdown_pct, 4),
            "high_water_mark": round(self.high_water_mark, 2),
            "current_equity": round(self.current_equity, 2),
            "reason": self.reason,
        }


class CircuitBreaker:
    """
    Monitors portfolio health continuously.

    Three states:
    - NORMAL: All trading allowed
    - CAUTION: Reduce position sizes by 50%, no new positions
    - HALTED: No new trades, requires manual reset
    """

    def __init__(self):
        cfg = get_config().risk
        self._daily_dd_halt = cfg.daily_drawdown_halt_pct
        self._total_dd_halt = cfg.total_drawdown_halt_pct

        # Caution triggers at 60% of halt level
        self._daily_dd_caution = cfg.daily_drawdown_halt_pct * 0.6
        self._total_dd_caution = cfg.total_drawdown_halt_pct * 0.6

        self._state = CircuitState.NORMAL
        self._high_water_mark: float = 0.0
        self._day_start_equity: float = 0.0

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def high_water_mark(self) -> float:
        return self._high_water_mark

    def initialize(self, equity: float, high_water_mark: Optional[float] = None):
        """Set starting equity for the day and all-time high-water mark."""
        self._day_start_equity = equity
        self._high_water_mark = high_water_mark or equity
        logger.info(
            "Circuit breaker initialized: equity=$%.2f, HWM=$%.2f",
            equity, self._high_water_mark,
        )

    def update(self, current_equity: float) -> CircuitBreakerStatus:
        """
        Update with current equity and return the circuit breaker status.
        Automatically transitions between NORMAL → CAUTION → HALTED.
        """
        # Update high-water mark
        if current_equity > self._high_water_mark:
            self._high_water_mark = current_equity

        # Calculate drawdowns
        daily_pnl_pct = 0.0
        if self._day_start_equity > 0:
            daily_pnl_pct = (
                (current_equity - self._day_start_equity) / self._day_start_equity
            )

        total_dd_pct = 0.0
        if self._high_water_mark > 0:
            total_dd_pct = (
                (self._high_water_mark - current_equity) / self._high_water_mark
            )

        reason = None
        prev_state = self._state

        # ── Check for HALTED ───────────────────────────────────
        if self._state != CircuitState.HALTED:
            if daily_pnl_pct < -self._daily_dd_halt:
                self._state = CircuitState.HALTED
                reason = (
                    f"Daily drawdown {daily_pnl_pct:.2%} exceeded "
                    f"halt threshold {-self._daily_dd_halt:.2%}"
                )
            elif total_dd_pct > self._total_dd_halt:
                self._state = CircuitState.HALTED
                reason = (
                    f"Total drawdown {total_dd_pct:.2%} exceeded "
                    f"halt threshold {self._total_dd_halt:.2%}"
                )

        # ── Check for CAUTION ──────────────────────────────────
        if self._state == CircuitState.NORMAL:
            if daily_pnl_pct < -self._daily_dd_caution:
                self._state = CircuitState.CAUTION
                reason = (
                    f"Daily drawdown {daily_pnl_pct:.2%} approaching "
                    f"halt threshold — entering CAUTION"
                )
            elif total_dd_pct > self._total_dd_caution:
                self._state = CircuitState.CAUTION
                reason = (
                    f"Total drawdown {total_dd_pct:.2%} approaching "
                    f"halt threshold — entering CAUTION"
                )

        # Log state transitions
        if self._state != prev_state:
            logger.warning(
                "CIRCUIT BREAKER: %s → %s — %s",
                prev_state.value, self._state.value, reason,
            )

        return CircuitBreakerStatus(
            state=self._state,
            daily_pnl_pct=daily_pnl_pct,
            total_drawdown_pct=total_dd_pct,
            high_water_mark=self._high_water_mark,
            current_equity=current_equity,
            reason=reason,
        )

    def manual_reset(self, current_equity: float):
        """
        Manually reset the circuit breaker to NORMAL.
        Only callable from the dashboard after human review.
        """
        logger.warning(
            "CIRCUIT BREAKER MANUAL RESET: %s → NORMAL (equity=$%.2f)",
            self._state.value, current_equity,
        )
        self._state = CircuitState.NORMAL
        self._day_start_equity = current_equity

    def reset_daily(self, equity: float):
        """Reset daily tracking at market open."""
        self._day_start_equity = equity
        if self._state == CircuitState.CAUTION:
            self._state = CircuitState.NORMAL
            logger.info("Circuit breaker auto-reset from CAUTION at new day")
