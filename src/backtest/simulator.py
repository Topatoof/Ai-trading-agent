"""
Trade Simulator — Simulates order fills with slippage and commission.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SimulatedTrade:
    """Record of a simulated trade."""
    symbol: str
    side: str               # BUY / SELL
    qty: int
    price: float            # Fill price (after slippage)
    timestamp: datetime | str
    signal_score: float
    reasoning: str
    pnl: float = 0.0        # Realized P&L (for sells)
    pnl_pct: float = 0.0


@dataclass
class SimulatedPosition:
    """Tracks a simulated open position."""
    symbol: str
    qty: int
    avg_entry_price: float
    entry_date: datetime | str


class TradeSimulator:
    """
    Simulates trades with configurable slippage and commission.
    Tracks positions, cash, and equity over time.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        slippage_pct: float = 0.0005,
        commission: float = 0.0,
        max_positions: int = 15,
        position_size_pct: float = 0.10,
    ):
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.commission = commission
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct

        self.positions: Dict[str, SimulatedPosition] = {}
        self.trades: List[SimulatedTrade] = []
        self.equity_curve: List[Dict] = []

    def buy(
        self,
        symbol: str,
        price: float,
        timestamp,
        signal_score: float,
        reasoning: str,
    ) -> Optional[SimulatedTrade]:
        """Simulate a buy order."""
        if symbol in self.positions:
            return None  # Already holding
        if len(self.positions) >= self.max_positions:
            return None  # Position limit

        # Calculate position size
        equity = self.get_equity({
            sym: pos.avg_entry_price  # Approximate
            for sym, pos in self.positions.items()
        })
        max_value = self.position_size_pct * equity
        max_value = min(max_value, self.cash)

        if max_value <= 0:
            return None

        # Apply slippage (buy at slightly higher price)
        fill_price = price * (1 + self.slippage_pct)
        qty = int(max_value / fill_price)

        if qty <= 0:
            return None

        cost = qty * fill_price + self.commission
        if cost > self.cash:
            qty = int((self.cash - self.commission) / fill_price)
            if qty <= 0:
                return None
            cost = qty * fill_price + self.commission

        self.cash -= cost
        self.positions[symbol] = SimulatedPosition(
            symbol=symbol,
            qty=qty,
            avg_entry_price=fill_price,
            entry_date=timestamp,
        )

        trade = SimulatedTrade(
            symbol=symbol,
            side="BUY",
            qty=qty,
            price=fill_price,
            timestamp=timestamp,
            signal_score=signal_score,
            reasoning=reasoning,
        )
        self.trades.append(trade)
        return trade

    def sell(
        self,
        symbol: str,
        price: float,
        timestamp,
        signal_score: float,
        reasoning: str,
    ) -> Optional[SimulatedTrade]:
        """Simulate a sell order."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Apply slippage (sell at slightly lower price)
        fill_price = price * (1 - self.slippage_pct)
        proceeds = pos.qty * fill_price - self.commission

        pnl = proceeds - (pos.qty * pos.avg_entry_price)
        pnl_pct = pnl / (pos.qty * pos.avg_entry_price) if pos.avg_entry_price > 0 else 0

        self.cash += proceeds
        del self.positions[symbol]

        trade = SimulatedTrade(
            symbol=symbol,
            side="SELL",
            qty=pos.qty,
            price=fill_price,
            timestamp=timestamp,
            signal_score=signal_score,
            reasoning=reasoning,
            pnl=pnl,
            pnl_pct=pnl_pct,
        )
        self.trades.append(trade)
        return trade

    def get_equity(self, current_prices: Dict[str, float]) -> float:
        """Calculate total equity (cash + position values)."""
        position_value = sum(
            pos.qty * current_prices.get(sym, pos.avg_entry_price)
            for sym, pos in self.positions.items()
        )
        return self.cash + position_value
