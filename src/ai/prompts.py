"""
Prompt Templates — Structured prompts for the Gemma 4 LLM.
Each prompt enforces a specific JSON output schema.
"""

# ── System Prompts ─────────────────────────────────────────────────

SYSTEM_BASE = """\
You are a professional quantitative trading analyst AI. You analyze \
technical indicators, market data, and portfolio state to make informed \
trading decisions. You always respond with valid JSON matching the \
requested schema. You are conservative and prioritize capital preservation. \
You never hallucinate data — you only use the data provided to you."""


SYSTEM_TRADE_ANALYST = SYSTEM_BASE + """

Your role is to evaluate stocks and generate trade signals. For each signal, \
you must provide:
1. A clear action (BUY, SELL, or HOLD)
2. A confidence score from 0.0 to 1.0
3. A concise reasoning trace (2-3 sentences)
4. A risk level assessment (LOW, MEDIUM, HIGH)

Key rules:
- RSI > 70 suggests overbought (potential sell), RSI < 30 suggests oversold (potential buy)
- MACD histogram crossing zero is a momentum change signal
- Price near Bollinger Band upper = caution for longs, lower = potential opportunity
- Confirm signals with volume (above-average volume strengthens signals)
- SMA crossovers (20 > 50 = bullish, 20 < 50 = bearish)
- Never recommend buying at 52-week highs without strong momentum confirmation
- Always consider the existing portfolio when making recommendations"""


SYSTEM_RISK_ASSESSOR = SYSTEM_BASE + """

Your role is to evaluate the risk of a proposed trade in the context of \
the existing portfolio. Consider:
1. Portfolio concentration (is this adding too much to one sector/stock?)
2. Correlation with existing positions
3. Current market conditions (breadth, volatility)
4. The AI confidence level of the trade signal
5. Drawdown proximity (how close to risk limits?)

You must be conservative. When in doubt, recommend against the trade."""


# ── User Prompt Templates ─────────────────────────────────────────

MARKET_ANALYSIS_PROMPT = """\
Analyze the following market data and generate trade signals for the \
most promising opportunities.

{market_state}

=== CURRENT PORTFOLIO ===
{portfolio_state}

=== INSTRUCTIONS ===
Review each symbol's indicators and identify:
1. Stocks showing strong buy signals (indicator confluence)
2. Stocks showing strong sell signals (indicator confluence)
3. Current positions that should be closed

Respond with valid JSON matching this schema:
{{
  "market_assessment": "brief overall market assessment (1-2 sentences)",
  "signals": [
    {{
      "symbol": "TICKER",
      "action": "BUY" | "SELL" | "HOLD",
      "confidence": 0.0-1.0,
      "reasoning": "2-3 sentence explanation citing specific indicators",
      "risk_level": "LOW" | "MEDIUM" | "HIGH",
      "suggested_order_type": "market" | "limit",
      "suggested_limit_price": null or price (for limit orders only)
    }}
  ]
}}

Only include signals with confidence >= 0.4. Maximum 5 signals per analysis. \
Do NOT include HOLD signals unless for an existing position that needs comment."""


TRADE_RISK_ASSESSMENT_PROMPT = """\
Evaluate the risk of the following proposed trade:

=== PROPOSED TRADE ===
Symbol: {symbol}
Action: {action}
Quantity: {qty}
Estimated Value: ${value:.2f}
AI Confidence: {confidence:.2f}
AI Reasoning: {reasoning}

=== CURRENT PORTFOLIO ===
{portfolio_state}

=== RISK LIMITS ===
- Max position size: {max_position_pct:.0%} of portfolio
- Max concurrent positions: {max_positions}
- Daily drawdown halt: {daily_dd:.0%}
- Total drawdown halt: {total_dd:.0%}
- Min confidence threshold: {min_confidence}
- Current circuit breaker state: {circuit_state}

=== MARKET CONDITIONS ===
{market_breadth}

Respond with valid JSON:
{{
  "approved": true | false,
  "risk_score": 0.0-1.0 (0=no risk, 1=extreme risk),
  "reasoning": "explanation of risk assessment",
  "concerns": ["list", "of", "specific", "concerns"],
  "suggested_modifications": {{
    "reduce_qty": null or suggested qty,
    "use_limit_order": true | false,
    "add_stop_loss": true | false
  }}
}}"""


POSITION_REVIEW_PROMPT = """\
Review the following open positions and recommend any actions:

=== OPEN POSITIONS ===
{positions}

=== MARKET STATE ===
{market_state}

For each position, assess whether to HOLD, ADD, REDUCE, or CLOSE.

Respond with valid JSON:
{{
  "position_reviews": [
    {{
      "symbol": "TICKER",
      "current_action": "HOLD" | "ADD" | "REDUCE" | "CLOSE",
      "confidence": 0.0-1.0,
      "reasoning": "brief explanation"
    }}
  ],
  "portfolio_summary": "1-2 sentence overall portfolio health assessment"
}}"""
