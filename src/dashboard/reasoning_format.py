"""
Turn dense indicator strings into short summaries + readable bullet lists.
"""
from __future__ import annotations

import re
from typing import Dict, List


def _segment_reasoning(raw: str) -> List[str]:
    if not raw or not str(raw).strip():
        return []
    text = str(raw).strip()
    parts = [p.strip() for p in text.split(";") if p.strip()]
    return parts if parts else [text]


def _humanize_segment(seg: str) -> str:
    s = seg.strip()
    if not s:
        return ""

    low = s.lower()

    m = re.search(r"rsi\s*=\s*([\d.]+)\s*(?:\(([^)]+)\))?", s, re.I)
    if m:
        val = m.group(1)
        mood = (m.group(2) or "").lower()
        try:
            v = float(val)
            if not mood:
                if v >= 70:
                    mood = "overbought"
                elif v <= 30:
                    mood = "oversold"
                else:
                    mood = "neutral"
        except ValueError:
            mood = mood or "neutral"
        return f"RSI is {mood} (reading {val})."

    if "macd" in low:
        if "histogram" in low and "positive" in low:
            return "MACD histogram is positive (short-term momentum building)."
        if "histogram" in low and "negative" in low:
            return "MACD histogram is negative (short-term momentum fading)."
        if "above signal" in low or ("macd" in low and "bullish" in low):
            return "MACD line is above its signal line (bullish crossover zone)."
        if "below signal" in low or ("macd" in low and "bearish" in low):
            return "MACD line is below its signal line (bearish crossover zone)."
        return f"MACD: {s[:120]}"

    if "bollinger" in low or "bb" in low:
        return f"Bollinger band context: {s[:120]}"

    if "sma" in low or "moving average" in low:
        return f"Moving average signal: {s[:120]}"

    if "atr" in low:
        return f"Volatility (ATR): {s[:120]}"

    if "stoch" in low:
        return f"Stochastic: {s[:120]}"

    if len(s) > 140:
        return s[:137] + "…"
    return s


def format_activity_reasoning(raw: str) -> Dict[str, str]:
    """
    Returns keys:
      summary: one friendly line for table preview
      details: multi-line bullets for the rationale column
    """
    segments = _segment_reasoning(raw)
    if not segments:
        return {"summary": "No written rationale was saved.", "details": "—"}

    friendly = [_humanize_segment(seg) for seg in segments]
    friendly = [f for f in friendly if f]

    summary = friendly[0] if friendly else segments[0][:100]
    if len(friendly) > 1 and len(summary) < 80:
        summary = f"{summary} (+{len(friendly) - 1} more signals below)"

    bullets = "\n".join(f"• {line}" for line in (friendly or segments))
    return {"summary": summary, "details": bullets}
