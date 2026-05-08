"""
Main Application Entry Point — Orchestrates the full trading loop.
"""

from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, time as dtime
from typing import Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from src.ai.decision_engine import DecisionEngine, TradeProposal
from src.config import get_config
from src.data.ingestion import MarketDataService
from src.data.indicators import IndicatorEngine
from src.data.market_state import MarketState, SymbolState
from src.execution.executor import TradeExecutor
from src.execution.portfolio import PortfolioManager
from src.execution.reconciliation import Reconciler
from src.logging.audit_logger import AuditLogger
from src.logging.models import DecisionLogEntry, SystemLogEntry
from src.risk.circuit_breaker import CircuitBreaker, CircuitState
from src.risk.manager import RiskManager
from src.risk.position_sizer import PositionSizer

logger = logging.getLogger(__name__)
ET = pytz.timezone("US/Eastern")

# Market hours
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)


class TradingApp:
    """
    Main application orchestrator.
    Initializes all components and runs the trading loop via APScheduler.
    """

    def __init__(self):
        self.cfg = get_config()
        self.audit = AuditLogger()
        self.portfolio = PortfolioManager()
        self.risk_manager = RiskManager()
        self.position_sizer = PositionSizer()
        self.circuit_breaker = CircuitBreaker()
        self.market_data = MarketDataService()
        self.indicator_engine = IndicatorEngine()
        self.decision_engine = DecisionEngine()
        self.reconciler = Reconciler(self.portfolio)
        self.executor = TradeExecutor(self.portfolio, self.risk_manager)
        self.scheduler = BackgroundScheduler()
        self._running = False

    def start(self):
        """Initialize and start the trading application."""
        self.audit.log_system(SystemLogEntry(
            event_type="startup",
            message="Trading application starting",
            details={"mode": self.cfg.trading.mode},
        ))

        # Initial sync with Alpaca
        logger.info("Syncing with Alpaca...")
        if self.reconciler.sync():
            self.circuit_breaker.initialize(
                equity=self.portfolio.total_equity,
                high_water_mark=self.portfolio.high_water_mark or self.portfolio.total_equity,
            )
            self.portfolio.day_start_equity = self.portfolio.total_equity
        else:
            logger.warning("Initial Alpaca sync failed — will retry")

        # Check LLM availability
        if self.decision_engine.check_llm():
            logger.info("✓ LM Studio connected (model: %s)", self.cfg.llm.model)
        else:
            logger.warning("✗ LM Studio not available — rule-based mode only")

        # Schedule jobs
        interval = self.cfg.trading.analysis_interval_minutes

        self.scheduler.add_job(
            self._analysis_loop,
            "interval",
            minutes=interval,
            id="analysis_loop",
            name="Market Analysis Loop",
        )

        self.scheduler.add_job(
            self._reconciliation_loop,
            "interval",
            minutes=5,
            id="reconciliation",
            name="Portfolio Reconciliation",
        )

        self.scheduler.add_job(
            self._snapshot_loop,
            "interval",
            minutes=1,
            id="snapshot",
            name="Portfolio Snapshot",
        )

        self.scheduler.start()
        self._running = True

        logger.info(
            "═══════════════════════════════════════════════════════════════"
        )
        logger.info(
            "  Trading App started — Mode: %s | Interval: %dmin | Universe: %d symbols",
            self.cfg.trading.mode.upper(),
            interval,
            len(self.cfg.trading.asset_universe),
        )
        logger.info(
            "═══════════════════════════════════════════════════════════════"
        )

    def stop(self):
        """Gracefully shut down the application."""
        self._running = False
        self.scheduler.shutdown(wait=False)
        self.portfolio.save_snapshot()
        self.audit.log_system(SystemLogEntry(
            event_type="shutdown",
            message="Trading application stopped",
        ))
        logger.info("Trading application stopped")

    def is_market_hours(self) -> bool:
        """Check if current time is within US market hours."""
        if not self.cfg.trading.trading_hours_only:
            return True
        now_et = datetime.now(ET).time()
        return MARKET_OPEN <= now_et <= MARKET_CLOSE

    # ── Scheduled Loops ────────────────────────────────────────

    def _analysis_loop(self):
        """Main analysis loop — runs every N minutes."""
        if self.cfg.trading.trading_hours_only and not self.is_market_hours():
            logger.debug("Outside market hours — skipping analysis")
            return

        if self.circuit_breaker.state == CircuitState.HALTED:
            logger.warning("Circuit breaker HALTED — skipping analysis")
            return

        try:
            self._run_analysis_cycle()
        except Exception as e:
            logger.error("Analysis cycle failed: %s", e, exc_info=True)

    def _reconciliation_loop(self):
        """Periodic reconciliation with Alpaca."""
        if not self.is_market_hours():
            return
        self.reconciler.sync()

    def _snapshot_loop(self):
        """Save portfolio snapshot every minute during market hours."""
        if not self.is_market_hours():
            return
        # Update circuit breaker
        status = self.circuit_breaker.update(self.portfolio.total_equity)
        if status.reason:
            self.audit.log_system(SystemLogEntry(
                event_type="circuit_breaker",
                message=status.reason,
                details=status.to_dict(),
            ))

    # ── Core Analysis Cycle ────────────────────────────────────

    def _run_analysis_cycle(self):
        """Single iteration of the analysis pipeline."""
        logger.info("━━━ Analysis cycle starting ━━━")

        # 1. Fetch market data
        logger.info("Fetching market data...")
        bars = self.market_data.get_historical_bars(days_back=200)
        latest = self.market_data.get_latest_bars()

        if not bars:
            logger.warning("No market data received — aborting cycle")
            return

        # 2. Compute indicators
        logger.info("Computing indicators...")
        indicator_snapshots = self.indicator_engine.compute_batch(bars)

        # 3. Build market state
        market_state = MarketState()
        for symbol, snap in indicator_snapshots.items():
            latest_bar = latest.get(symbol, {})
            prev_close = None
            if symbol in bars and len(bars[symbol]) >= 2:
                prev_close = float(bars[symbol]["close"].iloc[-2])

            current_price = snap.close or latest_bar.get("close", 0)
            daily_change = 0.0
            if prev_close and current_price:
                daily_change = (current_price - prev_close) / prev_close

            # Volume ratio
            vol_ratio = None
            if symbol in bars and len(bars[symbol]) >= 20:
                avg_vol = bars[symbol]["volume"].tail(20).mean()
                curr_vol = latest_bar.get("volume", 0)
                if avg_vol > 0:
                    vol_ratio = curr_vol / avg_vol

            market_state.symbols[symbol] = SymbolState(
                symbol=symbol,
                current_price=current_price,
                daily_change_pct=daily_change,
                volume=latest_bar.get("volume", 0),
                volume_ratio=vol_ratio,
                indicators=snap,
            )

        market_state.compute_breadth()

        # 4. Run AI decision engine
        logger.info(
            "Running AI analysis (breadth: %.2f, %d symbols)...",
            market_state.breadth_ratio, len(market_state.symbols),
        )
        proposals = self.decision_engine.analyze(
            market_state=market_state,
            portfolio_summary=self.portfolio.to_summary(),
            existing_positions=self.portfolio.held_symbols(),
        )

        logger.info("AI produced %d trade proposals", len(proposals))

        # 5. Size positions and evaluate risk
        execution_results = []
        risk_decisions = []

        for proposal in proposals:
            # Size the position
            if proposal.action == "BUY":
                pos_info = self.portfolio.positions.get(proposal.symbol)
                snap = indicator_snapshots.get(proposal.symbol)
                proposal.qty = self.position_sizer.calculate_qty(
                    symbol=proposal.symbol,
                    current_price=market_state.symbols[proposal.symbol].current_price,
                    portfolio_equity=self.portfolio.total_equity,
                    confidence=proposal.confidence,
                    atr=snap.atr if snap else None,
                    existing_qty=int(pos_info.qty) if pos_info else 0,
                    existing_value=pos_info.market_value if pos_info else 0.0,
                )
            elif proposal.action == "SELL":
                pos_info = self.portfolio.positions.get(proposal.symbol)
                if pos_info:
                    proposal.qty = self.position_sizer.calculate_sell_qty(
                        symbol=proposal.symbol,
                        held_qty=int(pos_info.qty),
                        confidence=proposal.confidence,
                    )
                else:
                    logger.warning("SELL signal for %s but no position held — skipping", proposal.symbol)
                    continue

            if not proposal.qty or proposal.qty <= 0:
                continue

            estimated_value = (
                proposal.qty
                * market_state.symbols[proposal.symbol].current_price
            )

            # Risk check
            risk_decision = self.risk_manager.evaluate(
                symbol=proposal.symbol,
                action=proposal.action,
                qty=proposal.qty,
                estimated_value=estimated_value,
                confidence=proposal.confidence,
                portfolio_equity=self.portfolio.total_equity,
                cash_available=self.portfolio.cash,
                current_positions=self.portfolio.position_values(),
                daily_pnl_pct=self.portfolio.daily_pnl_pct,
                total_drawdown_pct=self.portfolio.total_drawdown_pct,
            )
            risk_decisions.append(risk_decision.to_dict())

            # Execute or queue
            result = self.executor.process_proposal(proposal, risk_decision)
            execution_results.append(result)

        # 6. Log the complete decision cycle
        log_entry = DecisionLogEntry(
            mode=self.cfg.trading.mode,
            market_state_summary=market_state.to_llm_context(max_symbols=10),
            breadth_ratio=market_state.breadth_ratio,
            indicator_snapshots={
                sym: snap.to_dict()
                for sym, snap in list(indicator_snapshots.items())[:10]
            },
            trade_proposals=[p.to_dict() for p in proposals],
            risk_decisions=risk_decisions,
            execution_results=execution_results,
            portfolio_before={
                "equity": self.portfolio.total_equity,
                "cash": self.portfolio.cash,
                "positions": len(self.portfolio.positions),
            },
        )
        self.audit.log_decision(log_entry)

        logger.info("━━━ Analysis cycle complete ━━━")

    def run_single_analysis(self):
        """Run a single analysis cycle manually (for testing / dashboard trigger)."""
        self._run_analysis_cycle()


def main():
    """CLI entry point."""
    app = TradingApp()

    # Graceful shutdown on Ctrl+C
    def handle_signal(signum, frame):
        logger.info("Shutdown signal received...")
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.start()

    # Keep main thread alive
    logger.info("Press Ctrl+C to stop the application")
    try:
        while app._running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
