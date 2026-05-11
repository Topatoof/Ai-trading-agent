"""
Configuration module — Pydantic models that parse and validate settings.yaml + .env
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

# ── Resolve paths ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")


# ── Sub-config models ─────────────────────────────────────────────

class AlpacaConfig(BaseModel):
    api_key: str = ""
    secret_key: str = ""
    base_url: str = "https://paper-api.alpaca.markets"
    paper_mode: bool = True

    @model_validator(mode="before")
    @classmethod
    def load_from_env(cls, values: dict) -> dict:
        values["api_key"] = os.getenv("ALPACA_API_KEY", values.get("api_key", ""))
        values["secret_key"] = os.getenv("ALPACA_SECRET_KEY", values.get("secret_key", ""))
        base = os.getenv("ALPACA_BASE_URL")
        if base:
            values["base_url"] = base
        return values


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    model: str = "google/gemma-4-e4b"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_seconds: int = 120
    retry_attempts: int = 3
    retry_delay_seconds: int = 5

    @model_validator(mode="before")
    @classmethod
    def load_from_env(cls, values: dict) -> dict:
        base = os.getenv("LM_STUDIO_BASE_URL")
        if base:
            base = base.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            values["base_url"] = base
        key = os.getenv("LM_STUDIO_API_KEY") or os.getenv("LM_API_TOKEN")
        if key:
            values["api_key"] = key
        model = os.getenv("LM_STUDIO_MODEL")
        if model:
            values["model"] = model
        return values


class TradingConfig(BaseModel):
    mode: Literal["autonomous", "advisory"] = "advisory"
    max_trades_per_day: int = 10
    min_trade_interval_minutes: int = 15
    trading_hours_only: bool = True
    extended_hours: bool = False
    analysis_interval_minutes: int = 5
    asset_universe: List[str] = Field(default_factory=list)


class RiskConfig(BaseModel):
    max_position_pct: float = 0.10
    max_concurrent_positions: int = 15
    trailing_stop_pct: float = 0.03
    daily_drawdown_halt_pct: float = 0.05
    total_drawdown_halt_pct: float = 0.15
    min_confidence_threshold: float = 0.6
    half_kelly: bool = True


class IndicatorConfig(BaseModel):
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    sma_periods: List[int] = Field(default_factory=lambda: [20, 50, 200])
    atr_period: int = 14
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_smooth: int = 3


class DatabaseConfig(BaseModel):
    path: str = "data/portfolio.db"

    @property
    def full_path(self) -> Path:
        return PROJECT_ROOT / self.path

    @property
    def url(self) -> str:
        return f"sqlite:///{self.full_path}"


class LoggingConfig(BaseModel):
    decision_log_dir: str = "logs/decisions"
    level: str = "INFO"

    @property
    def full_log_dir(self) -> Path:
        return PROJECT_ROOT / self.decision_log_dir


# ── Root config ────────────────────────────────────────────────────

class AppConfig(BaseModel):
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    indicators: IndicatorConfig = Field(default_factory=IndicatorConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate application configuration from settings.yaml + .env."""
    config_path = path or CONFIG_DIR / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}
    return AppConfig(**raw)


# ── Singleton ──────────────────────────────────────────────────────
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Return the cached application config, loading it on first call."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
