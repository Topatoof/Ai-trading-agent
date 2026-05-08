"""
Audit Logger — Structured decision logging to JSON files and SQLite.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.config import get_config
from src.database import DecisionLog, get_session
from src.logging.models import DecisionLogEntry, SystemLogEntry, TradeLogEntry

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Logs all decisions as structured JSON.
    Dual output: daily JSON files + SQLite decision_log table.
    """

    def __init__(self):
        cfg = get_config().logging
        self._log_dir = cfg.full_log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._setup_python_logging(cfg.level)

    def _setup_python_logging(self, level: str):
        """Configure Python's standard logging."""
        root = logging.getLogger()
        root.setLevel(getattr(logging, level.upper(), logging.INFO))

        # Console handler
        if not root.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s │ %(levelname)-7s │ %(name)-30s │ %(message)s",
                datefmt="%H:%M:%S",
            )
            handler.setFormatter(formatter)
            root.addHandler(handler)

    def log_decision(self, entry: DecisionLogEntry):
        """Log a complete decision cycle."""
        # Write to JSON file
        self._write_json("decision", entry.model_dump(mode="json"))

        # Write to SQLite
        session = get_session()
        try:
            db_entry = DecisionLog(
                timestamp=entry.timestamp,
                market_state_json=entry.market_state_summary,
                indicators_json=json.dumps(entry.indicator_snapshots),
                llm_prompt=entry.llm_prompt,
                llm_response=entry.llm_response,
                signals_json=json.dumps(entry.rule_signals),
                trade_proposal_json=json.dumps(entry.trade_proposals),
                risk_decision_json=json.dumps(entry.risk_decisions),
                execution_result_json=json.dumps(entry.execution_results),
                portfolio_before_json=json.dumps(entry.portfolio_before),
                portfolio_after_json=json.dumps(entry.portfolio_after),
            )
            session.add(db_entry)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to log decision to DB: %s", e)
        finally:
            session.close()

    def log_trade(self, entry: TradeLogEntry):
        """Log a trade execution."""
        self._write_json("trade", entry.model_dump(mode="json"))

    def log_system(self, entry: SystemLogEntry):
        """Log a system-level event."""
        self._write_json("system", entry.model_dump(mode="json"))

    def _write_json(self, category: str, data: Dict[str, Any]):
        """Append a JSON log entry to the daily log file."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        filepath = self._log_dir / f"{category}_{today}.jsonl"

        try:
            with open(filepath, "a") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write %s log: %s", category, e)

    def get_recent_decisions(self, limit: int = 20) -> list:
        """Fetch recent decision logs from SQLite."""
        session = get_session()
        try:
            entries = (
                session.query(DecisionLog)
                .order_by(DecisionLog.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "market_state": e.market_state_json,
                    "trade_proposals": e.trade_proposal_json,
                    "risk_decisions": e.risk_decision_json,
                    "execution_results": e.execution_result_json,
                }
                for e in entries
            ]
        except Exception as e:
            logger.error("Failed to fetch decision logs: %s", e)
            return []
        finally:
            session.close()
