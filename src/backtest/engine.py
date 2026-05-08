"""
Backtesting Engine — Replays historical data through the decision engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.ai.signal_generator import SignalGenerator
from src.data.indicators import IndicatorEngine
from src.backtest.simulator import TradeSimulator, SimulatedTrade
from src.backtest.reporter import BacktestReporter

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    initial_capital: float = 100_000.0
    start_date: Optional[str] = None      # YYYY-MM-DD
    end_date: Optional[str] = None
    symbols: List[str] = field(default_factory=list)
    use_llm: bool = False                 # LLM adds latency — off by default
    slippage_pct: float = 0.0005          # 0.05%
    commission_per_trade: float = 0.0     # Alpaca is commission-free
    min_signal_score: float = 0.3         # Minimum rule-based score to act
    max_positions: int = 15
    position_size_pct: float = 0.10       # 10% of portfolio per position


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    config: BacktestConfig
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 0.0
    final_equity: float = 0.0
    total_return_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    equity_curve: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)


class BacktestEngine:
    """
    Replays historical data through the signal generator and simulates trading.
    Supports rule-based only mode (fast) or hybrid with LLM (slow).
    """

    def __init__(self):
        self._indicator_engine = IndicatorEngine()
        self._signal_gen = SignalGenerator()

    def run(
        self,
        historical_bars: Dict[str, pd.DataFrame],
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        Execute a backtest over historical data.

        Args:
            historical_bars: Dict of symbol → OHLCV DataFrame (daily).
            config: Backtest configuration.
        """
        logger.info("Starting backtest: %d symbols, capital=$%.0f", len(historical_bars), config.initial_capital)

        simulator = TradeSimulator(
            initial_capital=config.initial_capital,
            slippage_pct=config.slippage_pct,
            commission=config.commission_per_trade,
            max_positions=config.max_positions,
            position_size_pct=config.position_size_pct,
        )

        # Get common date range
        all_dates = set()
        for df in historical_bars.values():
            all_dates.update(df.index.tolist())
        sorted_dates = sorted(all_dates)

        if not sorted_dates:
            logger.error("No dates in historical data")
            return BacktestResult(config=config)

        # Minimum lookback for indicators (200 bars for SMA200)
        lookback = 200

        for i, date in enumerate(sorted_dates):
            if i < lookback:
                continue

            # Build indicator snapshots at this point in time
            snapshots = {}
            for symbol, df in historical_bars.items():
                # Get data up to this date
                mask = df.index <= date
                available = df[mask]

                if len(available) < 50:
                    continue

                snap = self._indicator_engine.compute(available, symbol)
                if snap.close:
                    snapshots[symbol] = snap

            if not snapshots:
                continue

            # Generate rule-based signals
            signals = self._signal_gen.generate_batch(snapshots)
            actionable = self._signal_gen.filter_actionable(signals, min_score=config.min_signal_score)

            # Process signals
            for sym, sig in actionable.items():
                current_price = snapshots[sym].close
                if not current_price:
                    continue

                if sig.score > config.min_signal_score and sym not in simulator.positions:
                    # Buy signal
                    simulator.buy(sym, current_price, date, sig.score, "; ".join(sig.details[:2]))

                elif sig.score < -config.min_signal_score and sym in simulator.positions:
                    # Sell signal
                    simulator.sell(sym, current_price, date, sig.score, "; ".join(sig.details[:2]))

            # Record equity curve point
            total_equity = simulator.get_equity(
                {sym: snapshots[sym].close for sym in simulator.positions if sym in snapshots and snapshots[sym].close}
            )
            simulator.equity_curve.append({
                "date": str(date),
                "equity": total_equity,
            })

        # Close all remaining positions at last known prices
        for sym in list(simulator.positions.keys()):
            if sym in historical_bars and len(historical_bars[sym]) > 0:
                last_price = float(historical_bars[sym]["close"].iloc[-1])
                simulator.sell(sym, last_price, sorted_dates[-1], 0.5, "End of backtest")

        # Generate results
        reporter = BacktestReporter()
        result = reporter.compute_metrics(simulator, config)

        logger.info(
            "Backtest complete: return=%.2f%%, trades=%d, win_rate=%.1f%%, max_dd=%.2f%%",
            result.total_return_pct * 100,
            result.total_trades,
            result.win_rate * 100,
            result.max_drawdown_pct * 100,
        )

        return result
