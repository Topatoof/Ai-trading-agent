"""
Signal Generator — Rule-based signal generation (independent of LLM).
Uses confluence of technical indicators to produce directional signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from src.data.indicators import IndicatorSnapshot

logger = logging.getLogger(__name__)


class SignalStrength(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class RuleSignal:
    """A single rule-based signal for a symbol."""
    symbol: str
    strength: SignalStrength
    score: float                # -1.0 (max bearish) to +1.0 (max bullish)
    bullish_count: int          # Number of bullish indicators
    bearish_count: int          # Number of bearish indicators
    total_indicators: int       # Total indicators evaluated
    details: List[str]          # Human-readable explanation of each indicator vote

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strength": self.strength.value,
            "score": round(self.score, 3),
            "bullish": self.bullish_count,
            "bearish": self.bearish_count,
            "total": self.total_indicators,
            "details": self.details,
        }


class SignalGenerator:
    """
    Rule-based signal generator. Evaluates indicator confluence to
    produce a directional signal per symbol. Acts as a first filter
    before LLM reasoning.
    """

    def generate(self, snapshot: IndicatorSnapshot) -> RuleSignal:
        """Generate a signal from an indicator snapshot."""
        bullish = 0
        bearish = 0
        total = 0
        details: List[str] = []

        # ── RSI ────────────────────────────────────────────────
        if snapshot.rsi is not None:
            total += 1
            if snapshot.rsi < 30:
                bullish += 1
                details.append(f"RSI={snapshot.rsi:.1f} (oversold → bullish)")
            elif snapshot.rsi < 40:
                bullish += 0.5
                details.append(f"RSI={snapshot.rsi:.1f} (approaching oversold → slight bullish)")
            elif snapshot.rsi > 70:
                bearish += 1
                details.append(f"RSI={snapshot.rsi:.1f} (overbought → bearish)")
            elif snapshot.rsi > 60:
                bearish += 0.5
                details.append(f"RSI={snapshot.rsi:.1f} (approaching overbought → slight bearish)")
            else:
                details.append(f"RSI={snapshot.rsi:.1f} (neutral)")

        # ── MACD ───────────────────────────────────────────────
        if snapshot.macd is not None and snapshot.macd_signal is not None:
            total += 1
            if snapshot.macd > snapshot.macd_signal:
                bullish += 1
                details.append("MACD above signal line (bullish)")
            else:
                bearish += 1
                details.append("MACD below signal line (bearish)")

            # Histogram momentum
            if snapshot.macd_histogram is not None:
                total += 1
                if snapshot.macd_histogram > 0 and snapshot.macd_histogram > 0:
                    bullish += 0.5
                    details.append(f"MACD histogram positive ({snapshot.macd_histogram:.4f})")
                elif snapshot.macd_histogram < 0:
                    bearish += 0.5
                    details.append(f"MACD histogram negative ({snapshot.macd_histogram:.4f})")

        # ── Bollinger Bands ────────────────────────────────────
        if snapshot.bb_pct is not None:
            total += 1
            if snapshot.bb_pct < 0.0:
                bullish += 1
                details.append(f"Price below lower Bollinger Band (%B={snapshot.bb_pct:.2f} → bullish)")
            elif snapshot.bb_pct < 0.2:
                bullish += 0.5
                details.append(f"Price near lower BB (%B={snapshot.bb_pct:.2f} → slight bullish)")
            elif snapshot.bb_pct > 1.0:
                bearish += 1
                details.append(f"Price above upper Bollinger Band (%B={snapshot.bb_pct:.2f} → bearish)")
            elif snapshot.bb_pct > 0.8:
                bearish += 0.5
                details.append(f"Price near upper BB (%B={snapshot.bb_pct:.2f} → slight bearish)")
            else:
                details.append(f"Price within Bollinger Bands (%B={snapshot.bb_pct:.2f})")

        # ── SMA Trend ──────────────────────────────────────────
        if snapshot.sma_20 is not None and snapshot.sma_50 is not None:
            total += 1
            if snapshot.sma_20 > snapshot.sma_50:
                bullish += 1
                details.append("SMA20 > SMA50 (bullish trend)")
            else:
                bearish += 1
                details.append("SMA20 < SMA50 (bearish trend)")

        if snapshot.price_vs_sma200 is not None:
            total += 1
            if snapshot.price_vs_sma200 > 0:
                bullish += 0.5
                details.append(f"Price above SMA200 ({snapshot.price_vs_sma200:+.2%})")
            else:
                bearish += 0.5
                details.append(f"Price below SMA200 ({snapshot.price_vs_sma200:+.2%})")

        # ── Stochastic ─────────────────────────────────────────
        if snapshot.stoch_k is not None and snapshot.stoch_d is not None:
            total += 1
            if snapshot.stoch_k < 20 and snapshot.stoch_d < 20:
                bullish += 1
                details.append(f"Stochastic oversold (K={snapshot.stoch_k:.1f}, D={snapshot.stoch_d:.1f})")
            elif snapshot.stoch_k > 80 and snapshot.stoch_d > 80:
                bearish += 1
                details.append(f"Stochastic overbought (K={snapshot.stoch_k:.1f}, D={snapshot.stoch_d:.1f})")
            elif snapshot.stoch_k > snapshot.stoch_d:
                bullish += 0.5
                details.append(f"Stochastic K > D (bullish cross)")
            else:
                bearish += 0.5
                details.append(f"Stochastic K < D (bearish cross)")

        # ── Compute composite score ────────────────────────────
        if total == 0:
            score = 0.0
        else:
            score = (bullish - bearish) / total  # Normalized to [-1, +1]

        # Map score to signal strength
        if score >= 0.5:
            strength = SignalStrength.STRONG_BUY
        elif score >= 0.2:
            strength = SignalStrength.BUY
        elif score <= -0.5:
            strength = SignalStrength.STRONG_SELL
        elif score <= -0.2:
            strength = SignalStrength.SELL
        else:
            strength = SignalStrength.NEUTRAL

        return RuleSignal(
            symbol=snapshot.symbol,
            strength=strength,
            score=score,
            bullish_count=int(bullish),
            bearish_count=int(bearish),
            total_indicators=total,
            details=details,
        )

    def generate_batch(
        self,
        snapshots: Dict[str, IndicatorSnapshot],
    ) -> Dict[str, RuleSignal]:
        """Generate signals for all symbols. Returns dict of symbol → signal."""
        return {
            symbol: self.generate(snap)
            for symbol, snap in snapshots.items()
        }

    def filter_actionable(
        self,
        signals: Dict[str, RuleSignal],
        min_score: float = 0.2,
    ) -> Dict[str, RuleSignal]:
        """Return only signals with abs(score) >= min_score (not NEUTRAL)."""
        return {
            sym: sig for sym, sig in signals.items()
            if abs(sig.score) >= min_score
        }
