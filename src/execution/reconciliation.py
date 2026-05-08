"""
Reconciliation — Syncs local state with Alpaca account.
"""

from __future__ import annotations

import logging
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import OrderSide, QueryOrderStatus

from src.config import get_config
from src.execution.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class Reconciler:
    """
    Syncs local portfolio state with Alpaca's authoritative state.
    Runs on startup and periodically during market hours.
    """

    def __init__(self, portfolio: PortfolioManager):
        cfg = get_config()
        self._client = TradingClient(
            api_key=cfg.alpaca.api_key,
            secret_key=cfg.alpaca.secret_key,
            paper=cfg.alpaca.paper_mode,
        )
        self._portfolio = portfolio

    def sync(self) -> bool:
        """
        Full sync: account info + positions from Alpaca → local state.
        Returns True if successful.
        """
        try:
            # Fetch account
            account = self._client.get_account()
            account_data = {
                "equity": str(account.equity),
                "cash": str(account.cash),
                "buying_power": str(account.buying_power),
                "portfolio_value": str(account.portfolio_value),
                "status": str(account.status),
            }

            # Fetch positions
            positions = self._client.get_all_positions()
            positions_data = []
            for pos in positions:
                positions_data.append({
                    "symbol": pos.symbol,
                    "qty": str(pos.qty),
                    "avg_entry_price": str(pos.avg_entry_price),
                    "current_price": str(pos.current_price),
                    "market_value": str(pos.market_value),
                    "unrealized_pl": str(pos.unrealized_pl),
                    "side": str(pos.side),
                })

            # Update portfolio
            self._portfolio.update_from_alpaca(account_data, positions_data)
            self._portfolio.save_snapshot()

            logger.info(
                "Reconciliation complete: equity=$%s, %d positions",
                account.equity, len(positions),
            )
            return True

        except Exception as e:
            logger.error("Reconciliation failed: %s", e)
            return False

    def get_open_orders(self) -> list:
        """Fetch open orders from Alpaca."""
        try:
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self._client.get_orders(request)
            return [
                {
                    "id": str(order.id),
                    "symbol": order.symbol,
                    "side": str(order.side),
                    "qty": str(order.qty),
                    "type": str(order.type),
                    "status": str(order.status),
                    "submitted_at": str(order.submitted_at),
                }
                for order in orders
            ]
        except Exception as e:
            logger.error("Failed to fetch open orders: %s", e)
            return []

    def get_account_status(self) -> Optional[dict]:
        """Get basic account status for health check."""
        try:
            account = self._client.get_account()
            return {
                "status": str(account.status),
                "equity": str(account.equity),
                "buying_power": str(account.buying_power),
                "trading_blocked": account.trading_blocked,
                "account_blocked": account.account_blocked,
            }
        except Exception as e:
            logger.error("Account status check failed: %s", e)
            return None
