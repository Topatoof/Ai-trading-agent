"""
Dashboard Application — Main Dash app with all 5 tabs.

Uses a persistent layout approach: all tab content is rendered at once
but hidden/shown via CSS, so callbacks always find their target components.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, dcc, html

from src.config import get_config
from src.dashboard.layouts.portfolio import create_portfolio_layout
from src.dashboard.layouts.trading import create_trading_layout
from src.dashboard.layouts.history import create_history_layout
from src.dashboard.layouts.backtest import create_backtest_layout
from src.dashboard.layouts.settings import create_settings_layout

logger = logging.getLogger(__name__)

# ── App reference (set by create_app) ──────────────────────────
_trading_app = None

TAB_IDS = ["portfolio", "trading", "history", "backtest", "settings"]


def create_app(trading_app=None):
    """Create and configure the Dash application."""
    global _trading_app
    _trading_app = trading_app

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        assets_folder="assets",
        suppress_callback_exceptions=True,
        title="AI Trading Dashboard",
        update_title=None,
    )

    # Build all tab contents up-front so every component ID exists at all times.
    # Visibility is toggled via the tab-switching callback.
    tab_contents = {
        "portfolio": create_portfolio_layout(),
        "trading": create_trading_layout(),
        "history": create_history_layout(),
        "backtest": create_backtest_layout(),
        "settings": create_settings_layout(),
    }

    app.layout = html.Div([
        # Auto-refresh intervals
        dcc.Interval(id="refresh-interval", interval=10_000, n_intervals=0),
        dcc.Interval(id="fast-refresh", interval=3_000, n_intervals=0),

        # Header
        html.Div([
            html.Div("⚡ AI Trading Agent", className="app-title"),
            html.Div([
                html.Div([
                    html.Span(className="status-dot green", id="alpaca-dot"),
                    html.Span("Alpaca", style={"fontSize": "12px"}),
                ], className="status-badge connected", id="alpaca-badge"),
                html.Div([
                    html.Span(className="status-dot green", id="llm-dot"),
                    html.Span("LM Studio", style={"fontSize": "12px"}),
                ], className="status-badge connected", id="llm-badge"),
                html.Div(
                    id="header-equity",
                    children="$0.00",
                    style={"fontSize": "18px", "fontWeight": "700",
                           "color": "#f1f5f9", "marginLeft": "12px"},
                ),
            ], className="header-status"),
        ], className="app-header"),

        # Tabs
        dcc.Tabs(
            id="main-tabs",
            value="portfolio",
            className="custom-tabs",
            children=[
                dcc.Tab(label="📊 Portfolio", value="portfolio", className="tab"),
                dcc.Tab(label="🤖 Trading", value="trading", className="tab"),
                dcc.Tab(label="📜 History", value="history", className="tab"),
                dcc.Tab(label="🔬 Backtest", value="backtest", className="tab"),
                dcc.Tab(label="⚙ Settings", value="settings", className="tab"),
            ],
        ),

        # All tab panels rendered at once, hidden/shown by callback
        html.Div([
            html.Div(tab_contents["portfolio"], id="panel-portfolio",
                     style={"display": "block", "marginTop": "20px"}),
            html.Div(tab_contents["trading"], id="panel-trading",
                     style={"display": "none", "marginTop": "20px"}),
            html.Div(tab_contents["history"], id="panel-history",
                     style={"display": "none", "marginTop": "20px"}),
            html.Div(tab_contents["backtest"], id="panel-backtest",
                     style={"display": "none", "marginTop": "20px"}),
            html.Div(tab_contents["settings"], id="panel-settings",
                     style={"display": "none", "marginTop": "20px"}),
        ]),
    ], id="app-container")

    _register_callbacks(app)
    return app


def _register_callbacks(app):
    """Register all dashboard callbacks."""

    # ── Tab switching (show/hide panels) ───────────────────
    @app.callback(
        [Output(f"panel-{tid}", "style") for tid in TAB_IDS],
        Input("main-tabs", "value"),
    )
    def switch_tab(active):
        return [
            {"display": "block", "marginTop": "20px"} if tid == active
            else {"display": "none", "marginTop": "20px"}
            for tid in TAB_IDS
        ]

    # ── Portfolio refresh callback ─────────────────────────
    @app.callback(
        [
            Output("header-equity", "children"),
            Output("total-equity", "children"),
            Output("daily-pnl", "children"),
            Output("daily-pnl", "className"),
            Output("cash-available", "children"),
            Output("open-positions", "children"),
            Output("drawdown", "children"),
            Output("total-pnl", "children"),
            Output("positions-table", "data"),
            Output("equity-curve-chart", "figure"),
            Output("allocation-chart", "figure"),
        ],
        Input("refresh-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def refresh_portfolio(n):
        if not _trading_app:
            raise dash.exceptions.PreventUpdate

        p = _trading_app.portfolio

        # Positions table data
        pos_data = []
        for pos in p.positions.values():
            pos_data.append({
                "symbol": pos.symbol,
                "qty": pos.qty,
                "avg_entry": pos.avg_entry_price,
                "current": pos.current_price,
                "market_value": pos.market_value,
                "pnl": pos.unrealized_pnl,
                "pnl_pct": pos.unrealized_pnl_pct,
            })

        daily_pnl = p.daily_pnl
        daily_cls = "metric-value positive" if daily_pnl >= 0 else "metric-value negative"

        eq_fig = _build_equity_chart()
        alloc_fig = _build_allocation_chart(p)

        return (
            f"${p.total_equity:,.2f}",
            f"${p.total_equity:,.2f}",
            f"${daily_pnl:+,.2f} ({p.daily_pnl_pct:+.2%})",
            daily_cls,
            f"${p.cash:,.2f}",
            str(p.position_count),
            f"{p.total_drawdown_pct:.2%}",
            f"${p.total_unrealized_pnl:+,.2f}",
            pos_data,
            eq_fig,
            alloc_fig,
        )

    # ── Trade history refresh ──────────────────────────────
    @app.callback(
        [
            Output("hist-total-trades", "children"),
            Output("hist-win-rate", "children"),
            Output("hist-realized-pnl", "children"),
            Output("trade-log-table", "data"),
            Output("cumulative-pnl-chart", "figure"),
        ],
        Input("refresh-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def refresh_history(n):
        from src.database import Trade, get_session
        session = get_session()
        try:
            trades = session.query(Trade).order_by(Trade.timestamp.desc()).limit(200).all()
            if not trades:
                raise dash.exceptions.PreventUpdate

            rows = []
            for t in trades:
                rows.append({
                    "timestamp": t.timestamp.strftime("%m/%d %H:%M") if t.timestamp else "",
                    "symbol": t.symbol,
                    "side": t.side,
                    "qty": t.qty,
                    "price": t.price,
                    "mode": t.mode,
                    "status": t.status,
                    "confidence": t.ai_confidence,
                    "pnl": t.pnl or 0,
                    "reasoning": (t.ai_reasoning or "")[:80],
                })

            sells = [t for t in trades if t.side == "SELL" and t.pnl is not None]
            total = len(sells)
            wins = sum(1 for t in sells if t.pnl and t.pnl > 0)
            realized = sum(t.pnl or 0 for t in sells)
            win_rate = f"{wins/total:.0%}" if total > 0 else "—"

            # Cumulative P&L chart
            cum_pnl = []
            running = 0
            for t in reversed(sells):
                running += (t.pnl or 0)
                cum_pnl.append({"time": t.timestamp, "pnl": running})

            fig = go.Figure()
            if cum_pnl:
                fig.add_trace(go.Scatter(
                    x=[p["time"] for p in cum_pnl],
                    y=[p["pnl"] for p in cum_pnl],
                    mode="lines+markers",
                    line=dict(color="#10b981" if running >= 0 else "#ef4444", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(16,185,129,0.08)" if running >= 0 else "rgba(239,68,68,0.08)",
                ))
            fig.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=16, r=16, t=16, b=16),
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickprefix="$"),
                font=dict(family="Inter", color="#94a3b8"), showlegend=False,
            )

            pnl_cls = "positive" if realized >= 0 else "negative"
            return (
                str(total),
                win_rate,
                f"${realized:+,.2f}",
                rows,
                fig,
            )
        except dash.exceptions.PreventUpdate:
            raise
        except Exception as e:
            logger.error("History refresh error: %s", e)
            raise dash.exceptions.PreventUpdate
        finally:
            session.close()

    # ── Recommendations refresh ────────────────────────────
    @app.callback(
        Output("recommendations-list", "children"),
        Input("fast-refresh", "n_intervals"),
        prevent_initial_call=True,
    )
    def refresh_recommendations(n):
        from src.database import Recommendation, get_session
        session = get_session()
        try:
            recs = session.query(Recommendation).filter_by(
                status="pending"
            ).order_by(Recommendation.created_at.desc()).limit(10).all()

            if not recs:
                return html.Div(
                    "No pending recommendations",
                    style={"textAlign": "center", "color": "#64748b",
                           "padding": "40px", "fontSize": "14px"},
                )

            cards = []
            for rec in recs:
                action_cls = "rec-action buy" if rec.action == "BUY" else "rec-action sell"
                cards.append(html.Div([
                    html.Div([
                        html.Span(rec.symbol, className="rec-symbol"),
                        html.Span(rec.action, className=action_cls),
                    ], className="rec-header"),
                    html.Div(f"{rec.qty} shares • Confidence: {rec.confidence:.0%}",
                             style={"fontSize": "12px", "color": "#94a3b8", "marginBottom": "6px"}),
                    html.Div(rec.reasoning or "", style={"fontSize": "12px", "color": "#64748b",
                                                          "marginBottom": "10px"}),
                    html.Div([
                        html.Button("✓ Approve", id={"type": "approve-rec", "index": rec.id},
                                    className="btn-primary btn-success",
                                    style={"fontSize": "11px", "padding": "6px 14px", "marginRight": "8px"}),
                        html.Button("✗ Reject", id={"type": "reject-rec", "index": rec.id},
                                    className="btn-primary btn-danger",
                                    style={"fontSize": "11px", "padding": "6px 14px"}),
                    ]),
                ], className="rec-card"))

            return cards

        except Exception as e:
            logger.error("Recommendations refresh error: %s", e)
            raise dash.exceptions.PreventUpdate
        finally:
            session.close()

    # ── Circuit breaker status ─────────────────────────────
    @app.callback(
        [
            Output("circuit-status", "children"),
            Output("circuit-status", "className"),
            Output("daily-dd-display", "children"),
            Output("total-dd-display", "children"),
        ],
        Input("fast-refresh", "n_intervals"),
        prevent_initial_call=True,
    )
    def refresh_circuit(n):
        if not _trading_app:
            raise dash.exceptions.PreventUpdate
        cb = _trading_app.circuit_breaker
        state = cb.state.value
        cls_map = {
            "NORMAL": "circuit-indicator circuit-normal",
            "CAUTION": "circuit-indicator circuit-caution",
            "HALTED": "circuit-indicator circuit-halted",
        }
        p = _trading_app.portfolio
        return (
            f"● {state}",
            cls_map.get(state, "circuit-indicator circuit-normal"),
            f"Daily DD: {p.daily_pnl_pct:.2%}",
            f"Total DD: {p.total_drawdown_pct:.2%}",
        )

    # ── Mode toggle callback ───────────────────────────────
    @app.callback(
        [
            Output("current-mode", "data"),
            Output("mode-status", "children"),
            Output("btn-advisory", "className"),
            Output("btn-autonomous", "className"),
        ],
        [Input("btn-advisory", "n_clicks"), Input("btn-autonomous", "n_clicks")],
        State("current-mode", "data"),
        prevent_initial_call=True,
    )
    def toggle_mode(adv_clicks, auto_clicks, current):
        ctx = callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        btn = ctx.triggered[0]["prop_id"].split(".")[0]
        if btn == "btn-advisory":
            mode = "advisory"
            msg = "Advisory mode — AI recommends, you approve"
        else:
            mode = "autonomous"
            msg = "⚠ Autonomous mode — AI trades automatically within risk limits"
        if _trading_app:
            _trading_app.executor.mode = mode
        adv_cls = "mode-btn active" if mode == "advisory" else "mode-btn"
        auto_cls = "mode-btn active" if mode == "autonomous" else "mode-btn"
        return mode, msg, adv_cls, auto_cls

    # ── Run analysis button ────────────────────────────────
    @app.callback(
        Output("action-result", "children"),
        Input("btn-run-analysis", "n_clicks"),
        prevent_initial_call=True,
    )
    def run_analysis(n):
        if _trading_app and n:
            from datetime import datetime
            import time
            start = time.time()
            try:
                _trading_app.run_single_analysis()
                elapsed = time.time() - start
                now = datetime.now().strftime("%H:%M:%S")
                return f"✅ Analysis complete at {now} ({elapsed:.1f}s) — check Pending Recommendations"
            except Exception as e:
                now = datetime.now().strftime("%H:%M:%S")
                return f"❌ Analysis failed at {now}: {e}"
        raise dash.exceptions.PreventUpdate

    # ── Sync portfolio button ──────────────────────────────
    @app.callback(
        Output("action-result", "children", allow_duplicate=True),
        Input("btn-sync-portfolio", "n_clicks"),
        prevent_initial_call=True,
    )
    def sync_portfolio(n):
        if _trading_app and n:
            _trading_app.reconciler.sync()
            return "Synced"
        raise dash.exceptions.PreventUpdate

    # ── Reset circuit breaker ──────────────────────────────
    @app.callback(
        Output("action-result", "children", allow_duplicate=True),
        Input("btn-reset-circuit", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_circuit(n):
        if _trading_app and n:
            _trading_app.circuit_breaker.manual_reset(_trading_app.portfolio.total_equity)
            _trading_app.risk_manager.set_circuit_state("NORMAL")
            return "Circuit breaker reset"
        raise dash.exceptions.PreventUpdate

    # ── Settings: health indicators ────────────────────────
    @app.callback(
        [
            Output("alpaca-health", "children"),
            Output("llm-health", "children"),
            Output("db-health", "children"),
            Output("scheduler-health", "children"),
        ],
        Input("refresh-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def refresh_health(n):
        alpaca = "connected" if _trading_app else "—"
        llm = "connected" if (_trading_app and _trading_app.decision_engine._llm_available) else "offline"
        db = "ok"
        sched = "running" if (_trading_app and _trading_app.scheduler.running) else "stopped"
        return alpaca, llm, db, sched

    # ── Settings: load audit log ───────────────────────────
    @app.callback(
        Output("audit-log-table", "data"),
        Input("refresh-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def refresh_audit_log(n):
        if not _trading_app:
            raise dash.exceptions.PreventUpdate
        logs = _trading_app.audit.get_recent_decisions(limit=20)
        return logs


def _build_equity_chart():
    """Build equity curve chart from portfolio snapshots."""
    from src.database import PortfolioSnapshot, get_session
    session = get_session()
    try:
        snaps = session.query(PortfolioSnapshot).order_by(
            PortfolioSnapshot.timestamp.asc()
        ).limit(1000).all()

        fig = go.Figure()
        if snaps:
            times = [s.timestamp for s in snaps]
            equities = [s.total_equity for s in snaps]
            fig.add_trace(go.Scatter(
                x=times, y=equities, mode="lines",
                line=dict(color="#3b82f6", width=2),
                fill="tozeroy",
                fillcolor="rgba(59,130,246,0.08)",
                name="Equity",
            ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=16, r=16, t=16, b=16),
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickprefix="$"),
            font=dict(family="Inter", color="#94a3b8"), showlegend=False,
        )
        return fig
    except Exception:
        return go.Figure()
    finally:
        session.close()


def _build_allocation_chart(portfolio):
    """Build asset allocation pie chart."""
    labels = ["Cash"]
    values = [portfolio.cash]
    colors = ["rgba(59,130,246,0.4)"]
    color_pool = [
        "#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444",
        "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#6366f1",
    ]
    for i, pos in enumerate(portfolio.positions.values()):
        labels.append(pos.symbol)
        values.append(pos.market_value)
        colors.append(color_pool[i % len(color_pool)])

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors),
        hole=0.65, textinfo="label",
        textfont=dict(color="#94a3b8", size=11),
    )])
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=16, r=16, t=16, b=16),
        showlegend=False, font=dict(family="Inter"),
    )
    return fig


def run_dashboard(trading_app=None, port: int = 8050, debug: bool = False):
    """Entry point to launch the dashboard server."""
    app = create_app(trading_app)
    logger.info("Starting dashboard on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
