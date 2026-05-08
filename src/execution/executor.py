"""
Trade Executor — Submits and manages orders via Alpaca.
Supports autonomous and advisory modes.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from src.ai.decision_engine import TradeProposal
from src.config import get_config
from src.database import Trade, Recommendation, get_session
from src.execution.portfolio import PortfolioManager
from src.risk.manager import RiskDecision, RiskManager

logger = logging.getLogger(__name__)


class TradeExecutor:
    """
    Handles order submission in both autonomous and advisory modes.

    Autonomous: Submit orders directly to Alpaca.
    Advisory: Queue proposals as recommendations for user approval.
    """

    def __init__(
        self,
        portfolio: PortfolioManager,
        risk_manager: RiskManager,
    ):
        cfg = get_config()
        self._client = TradingClient(
            api_key=cfg.alpaca.api_key,
            secret_key=cfg.alpaca.secret_key,
            paper=cfg.alpaca.paper_mode,
        )
        self._portfolio = portfolio
        self._risk_manager = risk_manager
        self._mode = cfg.trading.mode

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str):
        if value in ("autonomous", "advisory"):
            logger.info("Execution mode changed: %s → %s", self._mode, value)
            self._mode = value

    def process_proposal(
        self,
        proposal: TradeProposal,
        risk_decision: RiskDecision,
    ) -> dict:
        """
        Process a risk-approved trade proposal.

        In autonomous mode: execute immediately.
        In advisory mode: queue as recommendation.

        Returns a result dict with status and details.
        """
        if not risk_decision.approved:
            logger.info(
                "Proposal rejected by risk manager: %s %s — %s",
                proposal.action, proposal.symbol,
                "; ".join(risk_decision.reasons),
            )
            return {
                "status": "rejected",
                "reason": "; ".join(risk_decision.reasons),
            }

        # Apply risk-modified quantity if any
        qty = risk_decision.modified_qty or proposal.qty
        if not qty or qty <= 0:
            return {"status": "rejected", "reason": "Invalid quantity"}

        if self._mode == "autonomous":
            return self._execute_order(proposal, qty)
        else:
            return self._queue_recommendation(proposal, qty)

    def _execute_order(self, proposal: TradeProposal, qty: int) -> dict:
        """Submit order directly to Alpaca."""
        try:
            side = OrderSide.BUY if proposal.action == "BUY" else OrderSide.SELL

            if proposal.order_type == "limit" and proposal.limit_price:
                request = LimitOrderRequest(
                    symbol=proposal.symbol,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=proposal.limit_price,
                )
            else:
                request = MarketOrderRequest(
                    symbol=proposal.symbol,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )

            order = self._client.submit_order(request)

            # Record in database
            self._record_trade(
                symbol=proposal.symbol,
                side=proposal.action,
                qty=qty,
                price=proposal.limit_price,
                order_type=proposal.order_type,
                status="SUBMITTED",
                alpaca_order_id=str(order.id),
                confidence=proposal.confidence,
                reasoning=proposal.reasoning,
            )

            # Record with risk manager
            self._risk_manager.record_trade(proposal.symbol)

            logger.info(
                "ORDER SUBMITTED: %s %d %s (order_id=%s, confidence=%.2f)",
                proposal.action, qty, proposal.symbol,
                order.id, proposal.confidence,
            )

            return {
                "status": "submitted",
                "order_id": str(order.id),
                "symbol": proposal.symbol,
                "action": proposal.action,
                "qty": qty,
            }

        except Exception as e:
            logger.error(
                "ORDER FAILED: %s %d %s — %s",
                proposal.action, qty, proposal.symbol, e,
            )
            self._record_trade(
                symbol=proposal.symbol,
                side=proposal.action,
                qty=qty,
                price=proposal.limit_price,
                order_type=proposal.order_type,
                status="FAILED",
                confidence=proposal.confidence,
                reasoning=f"Execution error: {e}",
            )
            return {"status": "failed", "error": str(e)}

    def _queue_recommendation(self, proposal: TradeProposal, qty: int) -> dict:
        """Queue a trade recommendation for user approval."""
        session = get_session()
        try:
            rec = Recommendation(
                created_at=datetime.utcnow(),
                symbol=proposal.symbol,
                action=proposal.action,
                qty=qty,
                confidence=proposal.confidence,
                reasoning=proposal.reasoning,
                risk_level=proposal.risk_level,
                status="pending",
            )
            session.add(rec)
            session.commit()
            rec_id = rec.id

            logger.info(
                "RECOMMENDATION QUEUED: %s %d %s (id=%d, confidence=%.2f)",
                proposal.action, qty, proposal.symbol,
                rec_id, proposal.confidence,
            )

            return {
                "status": "queued",
                "recommendation_id": rec_id,
                "symbol": proposal.symbol,
                "action": proposal.action,
                "qty": qty,
            }

        except Exception as e:
            session.rollback()
            logger.error("Failed to queue recommendation: %s", e)
            return {"status": "failed", "error": str(e)}
        finally:
            session.close()

    def approve_recommendation(self, rec_id: int, user_note: str = "") -> dict:
        """Approve and execute a pending recommendation (advisory mode)."""
        session = get_session()
        try:
            rec = session.query(Recommendation).filter_by(
                id=rec_id, status="pending"
            ).first()

            if not rec:
                return {"status": "not_found", "error": f"Recommendation {rec_id} not found or not pending"}

            # Execute the trade
            proposal = TradeProposal(
                symbol=rec.symbol,
                action=rec.action,
                qty=int(rec.qty),
                confidence=rec.confidence,
                reasoning=rec.reasoning,
                risk_level=rec.risk_level,
            )

            result = self._execute_order(proposal, int(rec.qty))

            # Update recommendation status
            rec.status = "approved"
            rec.resolved_at = datetime.utcnow()
            rec.user_note = user_note
            session.commit()

            return result

        except Exception as e:
            session.rollback()
            logger.error("Failed to approve recommendation %d: %s", rec_id, e)
            return {"status": "failed", "error": str(e)}
        finally:
            session.close()

    def reject_recommendation(self, rec_id: int, reason: str = "") -> dict:
        """Reject a pending recommendation."""
        session = get_session()
        try:
            rec = session.query(Recommendation).filter_by(
                id=rec_id, status="pending"
            ).first()

            if not rec:
                return {"status": "not_found"}

            rec.status = "rejected"
            rec.resolved_at = datetime.utcnow()
            rec.user_note = reason
            session.commit()

            logger.info("Recommendation %d rejected: %s", rec_id, reason)
            return {"status": "rejected", "recommendation_id": rec_id}

        except Exception as e:
            session.rollback()
            return {"status": "failed", "error": str(e)}
        finally:
            session.close()

    def _record_trade(self, **kwargs):
        """Record a trade execution in the database."""
        session = get_session()
        try:
            trade = Trade(
                timestamp=datetime.utcnow(),
                mode=self._mode,
                symbol=kwargs.get("symbol"),
                side=kwargs.get("side"),
                qty=kwargs.get("qty"),
                price=kwargs.get("price"),
                order_type=kwargs.get("order_type"),
                status=kwargs.get("status"),
                alpaca_order_id=kwargs.get("alpaca_order_id"),
                ai_confidence=kwargs.get("confidence"),
                ai_reasoning=kwargs.get("reasoning"),
                risk_decision=kwargs.get("risk_decision"),
            )
            session.add(trade)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to record trade: %s", e)
        finally:
            session.close()
