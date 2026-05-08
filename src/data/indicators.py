"""
Technical Indicators — Compute standard indicators on OHLCV DataFrames.
Uses the 'ta' library (Technical Analysis Library in Python).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd
from ta.momentum import RSIIndicator, StochRSIIndicator, StochasticOscillator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

from src.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class IndicatorSnapshot:
    """Computed indicator values for a single symbol at the latest bar."""
    symbol: str
    timestamp: Optional[pd.Timestamp] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    price_vs_sma20: Optional[float] = None
    price_vs_sma50: Optional[float] = None
    price_vs_sma200: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_pct: Optional[float] = None
    atr: Optional[float] = None
    obv: Optional[float] = None
    vwap: Optional[float] = None
    close: Optional[float] = None

    def to_dict(self) -> dict:
        def r(v, n=2):
            return round(v, n) if v is not None else None
        return {
            "symbol": self.symbol, "close": self.close,
            "rsi": r(self.rsi), "macd": r(self.macd, 4),
            "macd_signal": r(self.macd_signal, 4), "macd_histogram": r(self.macd_histogram, 4),
            "stoch_k": r(self.stoch_k), "stoch_d": r(self.stoch_d),
            "sma_20": r(self.sma_20), "sma_50": r(self.sma_50), "sma_200": r(self.sma_200),
            "price_vs_sma20": r(self.price_vs_sma20, 4),
            "price_vs_sma50": r(self.price_vs_sma50, 4),
            "price_vs_sma200": r(self.price_vs_sma200, 4),
            "bb_upper": r(self.bb_upper), "bb_middle": r(self.bb_middle),
            "bb_lower": r(self.bb_lower), "bb_pct": r(self.bb_pct, 4),
            "atr": r(self.atr), "obv": self.obv, "vwap": r(self.vwap),
        }


class IndicatorEngine:
    """Computes technical indicators on OHLCV DataFrames using the ta library."""

    def __init__(self):
        cfg = get_config().indicators
        self._rsi_period = cfg.rsi_period
        self._macd_fast = cfg.macd_fast
        self._macd_slow = cfg.macd_slow
        self._macd_signal = cfg.macd_signal
        self._bb_period = cfg.bb_period
        self._bb_std = cfg.bb_std
        self._sma_periods = cfg.sma_periods
        self._atr_period = cfg.atr_period
        self._stoch_k = cfg.stoch_k
        self._stoch_d = cfg.stoch_d

    def compute(self, df: pd.DataFrame, symbol: str) -> IndicatorSnapshot:
        """Compute all indicators on an OHLCV DataFrame."""
        if df.empty or len(df) < self._macd_slow + self._macd_signal:
            return IndicatorSnapshot(symbol=symbol)

        snap = IndicatorSnapshot(symbol=symbol)
        snap.close = float(df["close"].iloc[-1])
        snap.timestamp = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # SMAs
        for period in self._sma_periods:
            if len(df) >= period:
                sma = SMAIndicator(close=close, window=period)
                val = _safe(sma.sma_indicator().iloc[-1])
                setattr(snap, f"sma_{period}", val)
                if val and snap.close:
                    setattr(snap, f"price_vs_sma{period}", (snap.close - val) / val)

        # RSI
        if len(df) >= self._rsi_period + 1:
            rsi = RSIIndicator(close=close, window=self._rsi_period)
            snap.rsi = _safe(rsi.rsi().iloc[-1])

        # MACD
        if len(df) >= self._macd_slow + self._macd_signal:
            macd = MACD(close=close, window_fast=self._macd_fast,
                        window_slow=self._macd_slow, window_sign=self._macd_signal)
            snap.macd = _safe(macd.macd().iloc[-1])
            snap.macd_signal = _safe(macd.macd_signal().iloc[-1])
            snap.macd_histogram = _safe(macd.macd_diff().iloc[-1])

        # Bollinger Bands
        if len(df) >= self._bb_period:
            bb = BollingerBands(close=close, window=self._bb_period, window_dev=self._bb_std)
            snap.bb_upper = _safe(bb.bollinger_hband().iloc[-1])
            snap.bb_middle = _safe(bb.bollinger_mavg().iloc[-1])
            snap.bb_lower = _safe(bb.bollinger_lband().iloc[-1])
            snap.bb_pct = _safe(bb.bollinger_pband().iloc[-1])

        # ATR
        if len(df) >= self._atr_period + 1:
            atr = AverageTrueRange(high=high, low=low, close=close, window=self._atr_period)
            snap.atr = _safe(atr.average_true_range().iloc[-1])

        # Stochastic
        if len(df) >= self._stoch_k:
            stoch = StochasticOscillator(high=high, low=low, close=close,
                                         window=self._stoch_k, smooth_window=self._stoch_d)
            snap.stoch_k = _safe(stoch.stoch().iloc[-1])
            snap.stoch_d = _safe(stoch.stoch_signal().iloc[-1])

        # OBV
        obv = OnBalanceVolumeIndicator(close=close, volume=volume)
        snap.obv = _safe(obv.on_balance_volume().iloc[-1])

        # VWAP (if column exists)
        if "vwap" in df.columns and pd.notna(df["vwap"].iloc[-1]):
            snap.vwap = float(df["vwap"].iloc[-1])

        return snap

    def compute_batch(self, bars: Dict[str, pd.DataFrame]) -> Dict[str, IndicatorSnapshot]:
        results = {}
        for symbol, df in bars.items():
            try:
                results[symbol] = self.compute(df, symbol)
            except Exception as e:
                logger.error("Indicator computation failed for %s: %s", symbol, e)
                results[symbol] = IndicatorSnapshot(symbol=symbol)
        return results


def _safe(val) -> Optional[float]:
    if pd.isna(val):
        return None
    return float(val)
