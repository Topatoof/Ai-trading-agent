"""
Portfolio State Manager — Tracks portfolio equity, positions, and P&L.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.database import PortfolioSnapshot, Position as PositionRow, get_session

logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    """In-memory representation of a single position."""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_entry_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / self.cost_basis

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "qty": self.qty,
            "avg_entry_price": round(self.avg_entry_price, 2),
            "current_price": round(self.current_price, 2),
            "market_value": round(self.market_value, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 4),
        }


class PortfolioManager:
    """
    Manages portfolio state in memory and persists snapshots to SQLite.
    Syncs with Alpaca on startup and periodically.
    """

    def __init__(self):
        self.total_equity: float = 0.0
        self.cash: float = 0.0
        self.buying_power: float = 0.0
        self.positions: Dict[str, PositionInfo] = {}
        self.high_water_mark: float = 0.0
        self.day_start_equity: float = 0.0
        self.realized_pnl_today: float = 0.0
        self.realized_pnl_total: float = 0.0
        self._last_updated: Optional[datetime] = None

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def total_positions_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def daily_pnl(self) -> float:
        if self.day_start_equity == 0:
            return 0.0
        return self.total_equity - self.day_start_equity

    @property
    def daily_pnl_pct(self) -> float:
        if self.day_start_equity == 0:
            return 0.0
        return self.daily_pnl / self.day_start_equity

    @property
    def total_drawdown_pct(self) -> float:
        if self.high_water_mark == 0:
            return 0.0
        return (self.high_water_mark - self.total_equity) / self.high_water_mark

    def position_values(self) -> Dict[str, float]:
        """Return dict of symbol → market_value for risk manager."""
        return {sym: p.market_value for sym, p in self.positions.items()}

    def held_symbols(self) -> List[str]:
        """Return list of currently held symbols."""
        return list(self.positions.keys())

    def update_from_alpaca(self, account_data: dict, positions_data: list):
        """
        Sync state from Alpaca API response.

        Args:
            account_data: Dict from Alpaca account endpoint.
            positions_data: List of dicts from Alpaca positions endpoint.
        """
        self.total_equity = float(account_data.get("equity", 0))
        self.cash = float(account_data.get("cash", 0))
        self.buying_power = float(account_data.get("buying_power", 0))

        # Update high-water mark
        if self.total_equity > self.high_water_mark:
            self.high_water_mark = self.total_equity

        # Update positions
        self.positions.clear()
        for pos in positions_data:
            symbol = pos.get("symbol", "")
            self.positions[symbol] = PositionInfo(
                symbol=symbol,
                qty=float(pos.get("qty", 0)),
                avg_entry_price=float(pos.get("avg_entry_price", 0)),
                current_price=float(pos.get("current_price", 0)),
            )

        self._last_updated = datetime.utcnow()
        logger.info(
            "Portfolio synced: equity=$%.2f, cash=$%.2f, positions=%d",
            self.total_equity, self.cash, self.position_count,
        )

    def save_snapshot(self):
        """Persist current state to SQLite."""
        session = get_session()
        try:
            snapshot = PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                total_equity=self.total_equity,
                cash=self.cash,
                buying_power=self.buying_power,
                daily_pnl=self.daily_pnl,
                total_pnl=self.total_unrealized_pnl + self.realized_pnl_total,
                high_water_mark=self.high_water_mark,
            )
            session.add(snapshot)

            # Upsert positions
            session.query(PositionRow).delete()
            for pos in self.positions.values():
                session.add(PositionRow(
                    symbol=pos.symbol,
                    qty=pos.qty,
                    avg_entry_price=pos.avg_entry_price,
                    current_price=pos.current_price,
                    unrealized_pnl=pos.unrealized_pnl,
                    market_value=pos.market_value,
                    updated_at=datetime.utcnow(),
                ))

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to save portfolio snapshot: %s", e)
        finally:
            session.close()

    def to_summary(self) -> str:
        """Human-readable portfolio summary for LLM context."""
        lines = [
            f"Total Equity: ${self.total_equity:,.2f}",
            f"Cash: ${self.cash:,.2f}",
            f"Buying Power: ${self.buying_power:,.2f}",
            f"Open Positions: {self.position_count}",
            f"Daily P&L: ${self.daily_pnl:,.2f} ({self.daily_pnl_pct:+.2%})",
            f"Unrealized P&L: ${self.total_unrealized_pnl:,.2f}",
            f"High-Water Mark: ${self.high_water_mark:,.2f}",
            f"Drawdown from HWM: {self.total_drawdown_pct:.2%}",
            "",
        ]

        if self.positions:
            lines.append("Positions:")
            for pos in sorted(
                self.positions.values(),
                key=lambda p: abs(p.unrealized_pnl),
                reverse=True,
            ):
                lines.append(
                    f"  {pos.symbol}: {pos.qty} shares @ ${pos.avg_entry_price:.2f} "
                    f"→ ${pos.current_price:.2f} "
                    f"(P&L: ${pos.unrealized_pnl:+,.2f} / {pos.unrealized_pnl_pct:+.2%})"
                )
        else:
            lines.append("No open positions.")

        return "\n".join(lines)

    def positions_summary(self) -> str:
        """Compact position summary for LLM position review."""
        if not self.positions:
            return "No open positions."

        lines = []
        for pos in self.positions.values():
            lines.append(
                f"{pos.symbol}: {pos.qty} shares, entry=${pos.avg_entry_price:.2f}, "
                f"current=${pos.current_price:.2f}, P&L=${pos.unrealized_pnl:+,.2f} "
                f"({pos.unrealized_pnl_pct:+.2%})"
            )
        return "\n".join(lines)
