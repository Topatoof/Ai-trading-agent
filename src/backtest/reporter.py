"""
Backtest Reporter — Computes performance metrics and generates reports.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List

import numpy as np

from src.backtest.simulator import TradeSimulator

logger = logging.getLogger(__name__)


class BacktestReporter:
    """Computes performance metrics from backtest results."""

    def compute_metrics(self, simulator: TradeSimulator, config) -> "BacktestResult":
        """Compute all performance metrics from a completed backtest."""
        from src.backtest.engine import BacktestResult

        trades = simulator.trades
        equity_curve = simulator.equity_curve

        # Basic stats
        sell_trades = [t for t in trades if t.side == "SELL"]
        winning = [t for t in sell_trades if t.pnl > 0]
        losing = [t for t in sell_trades if t.pnl <= 0]

        total_trades = len(sell_trades)
        win_rate = len(winning) / total_trades if total_trades > 0 else 0.0

        avg_win = np.mean([t.pnl for t in winning]) if winning else 0.0
        avg_loss = abs(np.mean([t.pnl for t in losing])) if losing else 0.0

        total_wins = sum(t.pnl for t in winning)
        total_losses = abs(sum(t.pnl for t in losing))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        final_equity = simulator.cash
        total_return = (final_equity - config.initial_capital) / config.initial_capital

        # Equity curve metrics
        max_drawdown = 0.0
        if equity_curve:
            equities = [e["equity"] for e in equity_curve]
            peak = equities[0]
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, dd)

            # Sharpe and Sortino (annualized, assuming daily data)
            if len(equities) > 1:
                returns = np.diff(equities) / equities[:-1]
                sharpe = self._sharpe_ratio(returns)
                sortino = self._sortino_ratio(returns)
            else:
                sharpe = 0.0
                sortino = 0.0
        else:
            sharpe = 0.0
            sortino = 0.0

        result = BacktestResult(
            config=config,
            start_date=equity_curve[0]["date"] if equity_curve else "",
            end_date=equity_curve[-1]["date"] if equity_curve else "",
            initial_capital=config.initial_capital,
            final_equity=final_equity,
            total_return_pct=total_return,
            total_trades=total_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            avg_win=float(avg_win),
            avg_loss=float(avg_loss),
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            equity_curve=equity_curve,
            trades=[
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "qty": t.qty,
                    "price": round(t.price, 2),
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 4),
                    "timestamp": str(t.timestamp),
                    "reasoning": t.reasoning,
                }
                for t in trades
            ],
        )

        return result

    @staticmethod
    def _sharpe_ratio(returns, risk_free_rate: float = 0.04) -> float:
        """Annualized Sharpe ratio (assuming daily returns)."""
        if len(returns) < 2:
            return 0.0
        daily_rf = risk_free_rate / 252
        excess = returns - daily_rf
        std = np.std(excess)
        if std == 0:
            return 0.0
        return float(np.mean(excess) / std * math.sqrt(252))

    @staticmethod
    def _sortino_ratio(returns, risk_free_rate: float = 0.04) -> float:
        """Annualized Sortino ratio (uses downside deviation)."""
        if len(returns) < 2:
            return 0.0
        daily_rf = risk_free_rate / 252
        excess = returns - daily_rf
        downside = excess[excess < 0]
        if len(downside) == 0:
            return float('inf')
        downside_std = np.std(downside)
        if downside_std == 0:
            return 0.0
        return float(np.mean(excess) / downside_std * math.sqrt(252))
