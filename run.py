#!/usr/bin/env python3
"""
Unified launcher — starts the trading engine + dashboard in one process.

Usage:
    python run.py              # Start everything (advisory mode)
    python run.py --port 8080  # Custom dashboard port
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from src.main import TradingApp
from src.dashboard.app import create_app

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="AI Trading Agent")
    parser.add_argument("--port", type=int, default=8050, help="Dashboard port (default: 8050)")
    parser.add_argument("--debug", action="store_true", help="Enable Dash debug mode")
    args = parser.parse_args()

    # Start the trading engine (background scheduler)
    trading_app = TradingApp()
    trading_app.start()

    # Graceful shutdown
    def handle_signal(signum, frame):
        logger.info("Shutdown signal received...")
        trading_app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start the dashboard (blocking — runs Flask server on main thread)
    dash_app = create_app(trading_app)

    logger.info("Dashboard: http://localhost:%d", args.port)
    dash_app.run(host="0.0.0.0", port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
