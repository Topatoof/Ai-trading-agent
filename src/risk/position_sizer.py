"""
Position Sizer — Determines trade quantity based on risk constraints.
Implements half-Kelly criterion and ATR-based sizing.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from src.config import get_config

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Calculates position sizes using Kelly criterion (half-Kelly for safety)
    or ATR-based sizing.
    """

    def __init__(self):
        cfg = get_config().risk
        self._max_position_pct = cfg.max_position_pct
        self._half_kelly = cfg.half_kelly

    def calculate_qty(
        self,
        symbol: str,
        current_price: float,
        portfolio_equity: float,
        confidence: float,
        atr: Optional[float] = None,
        existing_qty: int = 0,
        existing_value: float = 0.0,
        win_rate: float = 0.55,         # Historical or assumed win rate
        avg_win_loss_ratio: float = 1.5, # Historical or assumed payoff ratio
    ) -> int:
        """
        Calculate the number of shares to buy.

        Uses half-Kelly criterion capped by max position size constraint.

        Args:
            symbol: Stock ticker.
            current_price: Current share price.
            portfolio_equity: Total portfolio value.
            confidence: AI confidence in the trade (0-1).
            atr: Average True Range (for ATR-based sizing alternative).
            existing_qty: Shares already held.
            existing_value: Market value of existing position.
            win_rate: Estimated probability of winning.
            avg_win_loss_ratio: Average win / average loss.
        """
        if current_price <= 0 or portfolio_equity <= 0:
            return 0

        # Max dollar amount for this position
        max_value = self._max_position_pct * portfolio_equity
        remaining_capacity = max(0, max_value - existing_value)

        if remaining_capacity <= 0:
            logger.info("%s: Position already at max capacity", symbol)
            return 0

        # ── Method 1: Kelly Criterion ──────────────────────────
        # Kelly% = W - (1-W)/R where W=win_rate, R=avg_win_loss_ratio
        kelly_pct = win_rate - (1 - win_rate) / avg_win_loss_ratio

        if self._half_kelly:
            kelly_pct *= 0.5  # Half-Kelly for safety

        # Scale by AI confidence
        kelly_pct *= confidence

        # Clamp to [0, max_position_pct]
        kelly_pct = max(0, min(kelly_pct, self._max_position_pct))

        kelly_value = kelly_pct * portfolio_equity
        kelly_value = min(kelly_value, remaining_capacity)
        kelly_qty = int(kelly_value / current_price)

        # ── Method 2: ATR-based sizing (if ATR available) ──────
        atr_qty = None
        if atr and atr > 0:
            # Risk 1% of portfolio per ATR unit
            risk_per_trade = 0.01 * portfolio_equity
            atr_qty = int(risk_per_trade / atr)
            atr_qty = min(atr_qty, int(remaining_capacity / current_price))

        # ── Choose the more conservative ───────────────────────
        if atr_qty is not None:
            final_qty = min(kelly_qty, atr_qty)
        else:
            final_qty = kelly_qty

        final_qty = max(1, final_qty)  # At least 1 share

        # Verify we don't exceed max position
        total_value = (existing_qty + final_qty) * current_price
        if total_value > max_value:
            final_qty = max(1, int((max_value / current_price) - existing_qty))

        logger.debug(
            "%s: qty=%d (kelly=%d, atr=%s, price=%.2f, confidence=%.2f)",
            symbol, final_qty, kelly_qty,
            atr_qty if atr_qty else "N/A", current_price, confidence,
        )

        return final_qty

    def calculate_sell_qty(
        self,
        symbol: str,
        held_qty: int,
        confidence: float,
        action_strength: str = "FULL",  # FULL / PARTIAL
    ) -> int:
        """
        Calculate shares to sell.

        For FULL: sell all shares.
        For PARTIAL: sell proportional to confidence.
        """
        if action_strength == "FULL":
            return held_qty

        # Partial: sell confidence * held_qty, minimum 1
        sell_qty = max(1, int(held_qty * confidence))
        return min(sell_qty, held_qty)
