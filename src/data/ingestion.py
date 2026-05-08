"""
Data Ingestion — Alpaca market data fetching with local caching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestBarRequest,
    StockSnapshotRequest,
)
from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame

from src.config import get_config

logger = logging.getLogger(__name__)


class MarketDataService:
    """Wraps Alpaca's StockHistoricalDataClient for historical and real-time data."""

    def __init__(self):
        cfg = get_config()
        self._client = StockHistoricalDataClient(
            api_key=cfg.alpaca.api_key,
            secret_key=cfg.alpaca.secret_key,
        )
        self._universe = cfg.trading.asset_universe

    # ── Historical bars ────────────────────────────────────────────

    def get_historical_bars(
        self,
        symbols: List[str] | None = None,
        timeframe: TimeFrame = TimeFrame.Day,
        days_back: int = 200,
        end: datetime | None = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical OHLCV bars for each symbol.

        Returns a dict mapping symbol → DataFrame with columns:
            open, high, low, close, volume, vwap, trade_count, timestamp
        """
        symbols = symbols or self._universe
        end_dt = end or datetime.utcnow()
        start_dt = end_dt - timedelta(days=days_back)

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            feed=DataFeed.IEX,  # Free tier — IEX exchange data
        )

        try:
            bars = self._client.get_stock_bars(request)
            result: Dict[str, pd.DataFrame] = {}

            # Use .data dict — the `in` operator on BarSet is unreliable
            bars_data = bars.data if hasattr(bars, 'data') else {}

            for symbol in symbols:
                symbol_bars = bars_data.get(symbol, [])
                if not symbol_bars:
                    logger.warning("No bars returned for %s", symbol)
                    continue

                rows = []
                for bar in symbol_bars:
                    rows.append({
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "vwap": float(bar.vwap) if bar.vwap else None,
                        "trade_count": int(bar.trade_count) if bar.trade_count else None,
                    })

                df = pd.DataFrame(rows)
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)
                result[symbol] = df

            logger.info("Fetched historical bars for %d symbols", len(result))
            return result

        except Exception as e:
            logger.error("Failed to fetch historical bars: %s", e)
            raise

    # ── Latest bars ────────────────────────────────────────────────

    def get_latest_bars(
        self,
        symbols: List[str] | None = None,
    ) -> Dict[str, dict]:
        """Fetch the latest bar for each symbol. Returns dict of symbol → bar dict."""
        symbols = symbols or self._universe

        request = StockLatestBarRequest(
            symbol_or_symbols=symbols,
            feed=DataFeed.IEX,
        )

        try:
            bars = self._client.get_stock_latest_bar(request)
            result = {}
            for symbol, bar in bars.items():
                result[symbol] = {
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                    "vwap": float(bar.vwap) if bar.vwap else None,
                }
            return result

        except Exception as e:
            logger.error("Failed to fetch latest bars: %s", e)
            raise

    # ── Snapshots ──────────────────────────────────────────────────

    def get_snapshots(
        self,
        symbols: List[str] | None = None,
    ) -> Dict[str, dict]:
        """Fetch full snapshots (latest trade, quote, bar, prev bar) per symbol."""
        symbols = symbols or self._universe

        request = StockSnapshotRequest(
            symbol_or_symbols=symbols,
            feed=DataFeed.IEX,
        )

        try:
            snapshots = self._client.get_stock_snapshot(request)
            result = {}
            for symbol, snap in snapshots.items():
                result[symbol] = {
                    "latest_trade": {
                        "price": float(snap.latest_trade.price),
                        "size": int(snap.latest_trade.size),
                        "timestamp": snap.latest_trade.timestamp,
                    } if snap.latest_trade else None,
                    "latest_quote": {
                        "bid": float(snap.latest_quote.bid_price),
                        "ask": float(snap.latest_quote.ask_price),
                        "bid_size": int(snap.latest_quote.bid_size),
                        "ask_size": int(snap.latest_quote.ask_size),
                    } if snap.latest_quote else None,
                    "latest_bar": {
                        "open": float(snap.daily_bar.open),
                        "high": float(snap.daily_bar.high),
                        "low": float(snap.daily_bar.low),
                        "close": float(snap.daily_bar.close),
                        "volume": int(snap.daily_bar.volume),
                    } if snap.daily_bar else None,
                    "prev_daily_bar": {
                        "close": float(snap.previous_daily_bar.close),
                        "volume": int(snap.previous_daily_bar.volume),
                    } if snap.previous_daily_bar else None,
                }
            return result

        except Exception as e:
            logger.error("Failed to fetch snapshots: %s", e)
            raise
