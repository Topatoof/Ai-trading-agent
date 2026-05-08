"""
Logging Models — Pydantic models for structured log entries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DecisionLogEntry(BaseModel):
    """Complete audit trail for a single AI decision cycle."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    mode: str = "advisory"                  # autonomous / advisory

    # Market context
    market_state_summary: str = ""
    breadth_ratio: Optional[float] = None

    # Indicators that influenced the decision
    indicator_snapshots: Dict[str, Any] = Field(default_factory=dict)

    # Rule-based signals
    rule_signals: Dict[str, Any] = Field(default_factory=dict)

    # LLM interaction
    llm_prompt: str = ""
    llm_response: str = ""
    llm_latency_ms: Optional[int] = None

    # Trade proposals
    trade_proposals: List[Dict[str, Any]] = Field(default_factory=list)

    # Risk decisions
    risk_decisions: List[Dict[str, Any]] = Field(default_factory=list)

    # Execution results
    execution_results: List[Dict[str, Any]] = Field(default_factory=list)

    # Portfolio state
    portfolio_before: Dict[str, Any] = Field(default_factory=dict)
    portfolio_after: Dict[str, Any] = Field(default_factory=dict)


class TradeLogEntry(BaseModel):
    """Log entry for a single trade execution."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str
    side: str                               # BUY / SELL
    qty: float
    price: Optional[float] = None
    order_type: str = "market"
    status: str = "submitted"               # submitted / filled / failed
    alpaca_order_id: Optional[str] = None
    mode: str = "advisory"
    confidence: float = 0.0
    reasoning: str = ""
    risk_score: float = 0.0


class SystemLogEntry(BaseModel):
    """Log entry for system-level events."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str                         # startup / shutdown / error / circuit_breaker
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
