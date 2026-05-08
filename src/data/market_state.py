"""
Market State — Aggregated view combining price data + indicators for the AI engine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.data.indicators import IndicatorSnapshot

logger = logging.getLogger(__name__)


@dataclass
class SymbolState:
    """Complete state for a single symbol: price + indicators + metadata."""
    symbol: str
    current_price: float = 0.0
    daily_change_pct: float = 0.0
    volume: int = 0
    avg_volume_20d: Optional[float] = None
    volume_ratio: Optional[float] = None        # today_vol / avg_20d_vol
    indicators: Optional[IndicatorSnapshot] = None
    snapshot: Optional[dict] = None              # Alpaca snapshot data

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "daily_change_pct": round(self.daily_change_pct, 4),
            "volume": self.volume,
            "volume_ratio": round(self.volume_ratio, 2) if self.volume_ratio else None,
            "indicators": self.indicators.to_dict() if self.indicators else None,
        }


@dataclass
class MarketState:
    """
    Aggregated market state — the primary input to the AI decision engine.

    Captures the full picture: individual stock states, market breadth,
    and portfolio context.
    """
    timestamp: datetime = field(default_factory=datetime.utcnow)
    symbols: Dict[str, SymbolState] = field(default_factory=dict)

    # Market breadth summary
    advancing: int = 0          # Symbols with positive daily change
    declining: int = 0          # Symbols with negative daily change
    unchanged: int = 0
    breadth_ratio: float = 0.0  # advancing / (advancing + declining)

    # Sector groupings (optional enrichment)
    sector_performance: Dict[str, float] = field(default_factory=dict)

    def compute_breadth(self):
        """Compute market breadth statistics from symbol states."""
        self.advancing = sum(
            1 for s in self.symbols.values() if s.daily_change_pct > 0
        )
        self.declining = sum(
            1 for s in self.symbols.values() if s.daily_change_pct < 0
        )
        self.unchanged = len(self.symbols) - self.advancing - self.declining
        total = self.advancing + self.declining
        self.breadth_ratio = self.advancing / total if total > 0 else 0.5

    def get_top_movers(self, n: int = 5) -> Dict[str, List[SymbolState]]:
        """Return top gainers and losers by daily change %."""
        sorted_syms = sorted(
            self.symbols.values(),
            key=lambda s: s.daily_change_pct,
            reverse=True,
        )
        return {
            "gainers": sorted_syms[:n],
            "losers": sorted_syms[-n:][::-1],
        }

    def focused_copy(
        self,
        rule_signals: Optional[Dict] = None,
        max_symbols: int = 15,
    ) -> "MarketState":
        """
        Create a focused copy of this market state, prioritizing symbols with
        the strongest rule-based signals. Keeps the LLM context compact.
        """
        # Rank symbols: actionable signals first (by abs score), then by abs daily change
        def sort_key(sym: str):
            signal_score = 0.0
            if rule_signals and sym in rule_signals:
                signal_score = abs(rule_signals[sym].score)
            return (signal_score, abs(self.symbols[sym].daily_change_pct))

        ranked_syms = sorted(
            self.symbols.keys(),
            key=sort_key,
            reverse=True,
        )[:max_symbols]

        copy = MarketState(
            timestamp=self.timestamp,
            symbols={s: self.symbols[s] for s in ranked_syms},
            advancing=self.advancing,
            declining=self.declining,
            unchanged=self.unchanged,
            breadth_ratio=self.breadth_ratio,
            sector_performance=self.sector_performance,
        )
        return copy

    def to_llm_context(self, max_symbols: int = 20) -> str:
        """
        Serialize to a compact string suitable for LLM prompt context.
        Includes breadth summary + top opportunities.
        """
        lines = [
            f"=== MARKET STATE ({self.timestamp.strftime('%Y-%m-%d %H:%M UTC')}) ===",
            f"Breadth: {self.advancing} advancing, {self.declining} declining "
            f"(ratio: {self.breadth_ratio:.2f})",
            "",
        ]

        # Sort by absolute daily change to surface most active
        ranked = sorted(
            self.symbols.values(),
            key=lambda s: abs(s.daily_change_pct),
            reverse=True,
        )[:max_symbols]

        for sym_state in ranked:
            ind = sym_state.indicators
            ind_str = ""
            if ind:
                parts = []
                if ind.rsi is not None:
                    parts.append(f"RSI={ind.rsi:.1f}")
                if ind.macd_histogram is not None:
                    parts.append(f"MACD_H={ind.macd_histogram:.4f}")
                if ind.bb_pct is not None:
                    parts.append(f"BB%={ind.bb_pct:.2f}")
                if ind.stoch_k is not None:
                    parts.append(f"Stoch_K={ind.stoch_k:.1f}")
                if ind.price_vs_sma20 is not None:
                    parts.append(f"vs_SMA20={ind.price_vs_sma20:+.2%}")
                if ind.price_vs_sma50 is not None:
                    parts.append(f"vs_SMA50={ind.price_vs_sma50:+.2%}")
                if ind.atr is not None:
                    parts.append(f"ATR={ind.atr:.2f}")
                ind_str = " | " + " ".join(parts)

            vol_str = ""
            if sym_state.volume_ratio:
                vol_str = f" vol_ratio={sym_state.volume_ratio:.1f}x"

            lines.append(
                f"  {sym_state.symbol}: ${sym_state.current_price:.2f} "
                f"({sym_state.daily_change_pct:+.2%}){vol_str}{ind_str}"
            )

        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize to JSON for database logging."""
        return json.dumps({
            "timestamp": self.timestamp.isoformat(),
            "breadth": {
                "advancing": self.advancing,
                "declining": self.declining,
                "ratio": self.breadth_ratio,
            },
            "symbols": {
                sym: state.to_dict()
                for sym, state in self.symbols.items()
            },
        })
