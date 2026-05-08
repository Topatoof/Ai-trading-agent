# 🤖 Local-First AI Trading Agent

A semi-autonomous financial trading application powered by a locally-hosted LLM (Gemma 4 via LM Studio), interfacing with Alpaca's paper trading API.

## Features

- **Dual Mode Operation**: Advisory (AI recommends, you approve) and Autonomous (AI trades within constraints)
- **Technical Analysis**: 8+ indicators via pandas-ta (RSI, MACD, Bollinger Bands, SMAs, ATR, Stochastic, OBV, VWAP)
- **AI-Powered Decisions**: Gemma 4 LLM analyzes market data and generates trade signals with reasoning
- **Rule-Based Signals**: Technical indicator confluence scoring as a pre-filter for AI analysis
- **Risk Management**: Position limits, drawdown halts, circuit breaker, half-Kelly sizing
- **Real-Time Dashboard**: Premium dark-themed Dash/Plotly dashboard with 5 tabs
- **Backtesting Engine**: Replay historical data with performance metrics (Sharpe, Sortino, etc.)
- **Full Audit Trail**: Every AI decision logged to JSON + SQLite

## Prerequisites

- Python 3.11+
- [LM Studio](https://lmstudio.ai/) with `google/gemma-4-e4b` model loaded
- [Alpaca](https://alpaca.markets/) paper trading account

## Quick Start

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys (already set up in .env)
# Edit .env if needed

# 4. Start LM Studio and load the gemma-4-e4b model

# 5. Launch the trading agent + dashboard
python -m src.main        # Trading engine (background scheduler)
python -m src.dashboard.app  # Dashboard (http://localhost:8050)
```

## Architecture

```
Market Data → Indicators → Rule-Based Signals → AI Analysis → Risk Check → Execute/Queue
                                                    ↕
                                            Gemma 4 (LM Studio)
```

## Dashboard Tabs

1. **Portfolio** — Equity curve, positions, P&L, allocation pie chart
2. **Trading** — Mode toggle, circuit breaker, AI insights, pending recommendations
3. **History** — Trade log, cumulative P&L chart, win rate metrics
4. **Backtest** — Configure and run backtests, view equity curves and metrics
5. **Settings** — Risk parameters, system health, asset universe, audit logs

## Risk Controls

| Control | Default |
|---|---|
| Max position size | 10% of portfolio |
| Max concurrent positions | 15 |
| Trailing stop | 3% |
| Daily drawdown halt | 5% |
| Total drawdown halt | 15% |
| Min AI confidence | 0.6 |
| Max trades/day | 10 |
| Min trade interval | 15 minutes |

## License

Private — For personal use only.
