"""
Database module — SQLAlchemy models and session management.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_config


class Base(DeclarativeBase):
    pass


# ── ORM Models ─────────────────────────────────────────────────────

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    total_equity = Column(Float)
    cash = Column(Float)
    buying_power = Column(Float)
    daily_pnl = Column(Float)
    total_pnl = Column(Float)
    high_water_mark = Column(Float)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    qty = Column(Float)
    avg_entry_price = Column(Float)
    current_price = Column(Float)
    unrealized_pnl = Column(Float)
    market_value = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)       # BUY / SELL
    qty = Column(Float)
    price = Column(Float)
    order_type = Column(String)
    status = Column(String)                     # FILLED / CANCELLED / REJECTED
    alpaca_order_id = Column(String)
    mode = Column(String)                       # autonomous / advisory
    ai_confidence = Column(Float)
    ai_reasoning = Column(Text)
    risk_decision = Column(String)
    pnl = Column(Float)                         # Realized P&L for closing trades


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    symbol = Column(String, nullable=False)
    action = Column(String, nullable=False)
    qty = Column(Float)
    confidence = Column(Float)
    reasoning = Column(Text)
    risk_level = Column(String)
    status = Column(String, default="pending")  # pending / approved / rejected / expired
    resolved_at = Column(DateTime)
    user_note = Column(Text)


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    market_state_json = Column(Text)
    indicators_json = Column(Text)
    llm_prompt = Column(Text)
    llm_response = Column(Text)
    signals_json = Column(Text)
    trade_proposal_json = Column(Text)
    risk_decision_json = Column(Text)
    execution_result_json = Column(Text)
    portfolio_before_json = Column(Text)
    portfolio_after_json = Column(Text)


# ── Engine & Session ───────────────────────────────────────────────

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        cfg = get_config()
        cfg.database.full_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(cfg.database.url, echo=False)
        Base.metadata.create_all(_engine)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()
