#!/usr/bin/env python3
"""
Unified launcher — starts the trading engine + dashboard in one process.

Usage:
    python run.py                 # Dev: Dash debug + hot reload (default)
    python run.py --no-debug      # Production-style: no reload, no dev tools
    python run.py --port 8080     # Custom dashboard port
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

from src.main import TradingApp
from src.dashboard.app import create_app

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="AI Trading Agent")
    parser.add_argument("--port", type=int, default=8050, help="Dashboard port (default: 8050)")
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Disable Dash debug mode, dev tools, and hot reload (use for production-like runs)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    debug = (not args.no_debug) or args.debug

    # Start the trading engine (background scheduler). With Werkzeug's reloader
    # (debug=True), only start in the worker process to avoid double schedulers.
    trading_app = TradingApp()
    if (not debug) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
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

    logger.info(
        "Dashboard: http://localhost:%d (debug=%s, hot_reload=%s)",
        args.port,
        debug,
        debug,
    )
    dash_app.run(
        host="0.0.0.0",
        port=args.port,
        debug=debug,
        dev_tools_hot_reload=debug,
        use_reloader=debug,
    )


if __name__ == "__main__":
    main()
