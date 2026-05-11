"""
Dashboard Application — Main Dash app with all 5 tabs.

Uses a persistent layout approach: all tab content is rendered at once
but hidden/shown via CSS, so callbacks always find their target components.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback_context, dcc, html

from src.config import get_config
from src.dashboard.layouts.portfolio import create_portfolio_layout
from src.dashboard.layouts.trading import create_trading_layout
from src.dashboard.layouts.history import create_history_layout
from src.dashboard.layouts.backtest import create_backtest_layout
from src.dashboard.layouts.settings import create_settings_layout
from src.dashboard.reasoning_format import format_activity_reasoning

logger = logging.getLogger(__name__)

# ── App reference (set by create_app) ──────────────────────────
_trading_app = None


def _history_ts_key(dt: datetime | None) -> str:
    """ISO string safe for sorting (avoids naive/aware TypeError in sort)."""
    if dt is None:
        return ""
    try:
        if getattr(dt, "tzinfo", None) is not None:
            return dt.isoformat()
    except Exception:
        pass
    return dt.replace(tzinfo=None).isoformat()


def _dt_delta_seconds(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    try:
        return abs((a - b).total_seconds())
    except TypeError:
        a0 = a.replace(tzinfo=None) if getattr(a, "tzinfo", None) else a
        b0 = b.replace(tzinfo=None) if getattr(b, "tzinfo", None) else b
        return abs((a0 - b0).total_seconds())


def _match_approved_rec_for_trade(trade, approved_recs: list, window_sec: float = 300.0):
    """Pair an advisory trade with the approval that likely triggered it."""
    best = None
    best_d: float | None = None
    for r in approved_recs:
        if r.symbol != trade.symbol or r.action != trade.side:
            continue
        r_ts = r.resolved_at or r.created_at
        d = _dt_delta_seconds(trade.timestamp, r_ts)
        if d is None or d > window_sec:
            continue
        if best_d is None or d < best_d:
            best_d = d
            best = r
    return best

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
        [
            Input("refresh-interval", "n_intervals"),
            Input("main-tabs", "value"),
        ],
        prevent_initial_call=False,
    )
    def refresh_history(_n, active_tab):
        from sqlalchemy.sql import func

        from src.dashboard.layouts import history as history_layout
        from src.database import Recommendation, Trade, get_session

        if active_tab != "history":
            raise dash.exceptions.PreventUpdate

        session = get_session()
        try:
            trades = session.query(Trade).order_by(Trade.timestamp.desc()).limit(200).all()
            rejected = (
                session.query(Recommendation)
                .filter(Recommendation.status == "rejected")
                .order_by(
                    func.coalesce(
                        Recommendation.resolved_at,
                        Recommendation.created_at,
                    ).desc(),
                )
                .limit(200)
                .all()
            )
            approved = (
                session.query(Recommendation)
                .filter(Recommendation.status == "approved")
                .order_by(
                    func.coalesce(
                        Recommendation.resolved_at,
                        Recommendation.created_at,
                    ).desc(),
                )
                .limit(200)
                .all()
            )

            matched_rec_ids: set[int] = set()
            rows: list[dict] = []

            for t in trades:
                ts = t.timestamp
                conf = t.ai_confidence
                conf_s = f"{conf:.0%}" if conf is not None else "—"
                pnl_s = f"${t.pnl:+,.2f}" if t.pnl is not None else "$0.00"

                partner = None
                # Match approvals for advisory rows; also try when mode is missing in older DB rows.
                if (t.mode or "").lower() != "autonomous":
                    partner = _match_approved_rec_for_trade(t, approved)

                if partner:
                    matched_rec_ids.add(int(partner.id))
                    fr = format_activity_reasoning(partner.reasoning or t.ai_reasoning or "")
                    oid = (t.alpaca_order_id or "").strip()
                    status_bits = [t.status or "—"]
                    if oid:
                        status_bits.append(f"Alpaca order {oid}")
                    rows.append({
                        "_sort": ts,
                        "timestamp": ts.strftime("%m/%d %H:%M") if ts else "",
                        "kind": "Approved recommendation",
                        "symbol": t.symbol,
                        "side": t.side,
                        "qty": t.qty,
                        "price": t.price if t.price is not None else "—",
                        "mode": t.mode or "advisory",
                        "status": " · ".join(status_bits),
                        "confidence": conf_s,
                        "pnl": pnl_s,
                        "summary": fr["summary"],
                        "rationale": fr["details"],
                    })
                    continue

                fr = format_activity_reasoning(t.ai_reasoning or "")
                rows.append({
                    "_sort": ts,
                    "timestamp": ts.strftime("%m/%d %H:%M") if ts else "",
                    "kind": "Order placed",
                    "symbol": t.symbol,
                    "side": t.side,
                    "qty": t.qty,
                    "price": t.price if t.price is not None else "—",
                    "mode": t.mode or "—",
                    "status": t.status or "—",
                    "confidence": conf_s,
                    "pnl": pnl_s,
                    "summary": fr["summary"],
                    "rationale": fr["details"],
                })

            for r in approved:
                if int(r.id) in matched_rec_ids:
                    continue
                fr = format_activity_reasoning(r.reasoning or "")
                ts = r.resolved_at or r.created_at
                conf = r.confidence
                conf_s = f"{conf:.0%}" if conf is not None else "—"
                rows.append({
                    "_sort": ts,
                    "timestamp": ts.strftime("%m/%d %H:%M") if ts else "",
                    "kind": "Approved recommendation",
                    "symbol": r.symbol,
                    "side": r.action,
                    "qty": r.qty,
                    "price": "—",
                    "mode": "advisory",
                    "status": "Approved (no nearby order row — check Alpaca / logs)",
                    "confidence": conf_s,
                    "pnl": "—",
                    "summary": fr["summary"],
                    "rationale": fr["details"],
                })

            for r in rejected:
                fr = format_activity_reasoning(r.reasoning or "")
                ts = r.resolved_at or r.created_at
                conf = r.confidence
                conf_s = f"{conf:.0%}" if conf is not None else "—"
                note = (r.user_note or "").strip()
                rationale = fr["details"]
                if note:
                    rationale = f"{rationale}\n\nDecline note: {note}"
                rows.append({
                    "_sort": ts,
                    "timestamp": ts.strftime("%m/%d %H:%M") if ts else "",
                    "kind": "Declined recommendation",
                    "symbol": r.symbol,
                    "side": r.action,
                    "qty": r.qty,
                    "price": "—",
                    "mode": "—",
                    "status": "Rejected",
                    "confidence": conf_s,
                    "pnl": "—",
                    "summary": fr["summary"],
                    "rationale": rationale,
                })

            rows.sort(key=lambda x: _history_ts_key(x["_sort"]), reverse=True)
            for row in rows:
                row.pop("_sort", None)

            sells = [t for t in trades if t.side == "SELL" and t.pnl is not None]
            total = len(sells)
            wins = sum(1 for t in sells if t.pnl and t.pnl > 0)
            realized = sum(t.pnl or 0 for t in sells)
            win_rate = f"{wins/total:.0%}" if total > 0 else "—"

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

            if not trades and not rejected and not approved:
                return (
                    "0",
                    "—",
                    "$+0.00",
                    [],
                    history_layout._empty(),
                )

            return (
                str(total),
                win_rate,
                f"${realized:+,.2f}",
                rows,
                fig,
            )
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
                reasoning = (rec.reasoning or "").strip()
                parts = [p.strip() for p in reasoning.split(";") if p.strip()]
                thesis = parts[0] if parts else "No analysis summary provided."
                supporting = " | ".join(parts[1:3]) if len(parts) > 1 else "No additional supporting signals."
                created_text = rec.created_at.strftime("%H:%M:%S") if rec.created_at else "N/A"
                cards.append(html.Div([
                    html.Div([
                        html.Span(rec.symbol, className="rec-symbol"),
                        html.Span(rec.action, className=action_cls),
                    ], className="rec-header"),
                    html.Div(f"{rec.qty} shares • Confidence: {rec.confidence:.0%}",
                             style={"fontSize": "12px", "color": "#94a3b8", "marginBottom": "6px"}),
                    html.Div(
                        [
                            html.Div(
                                f"Summary: {thesis}",
                                style={"fontSize": "12px", "color": "#cbd5e1", "marginBottom": "4px"},
                            ),
                            html.Div(
                                f"Justification: {supporting}",
                                style={"fontSize": "12px", "color": "#94a3b8", "marginBottom": "4px"},
                            ),
                            html.Div(
                                f"Risk: {rec.risk_level or 'N/A'} • Created: {created_text}",
                                style={"fontSize": "11px", "color": "#64748b"},
                            ),
                        ],
                        style={
                            "background": "rgba(255,255,255,0.02)",
                            "border": "1px solid rgba(255,255,255,0.06)",
                            "borderRadius": "8px",
                            "padding": "8px 10px",
                            "marginBottom": "10px",
                        },
                    ),
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

    # ── Recommendation actions (approve/reject) ─────────────
    @app.callback(
        Output("action-result", "children", allow_duplicate=True),
        [
            Input({"type": "approve-rec", "index": ALL}, "n_clicks"),
            Input({"type": "reject-rec", "index": ALL}, "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def handle_recommendation_actions(approve_clicks, reject_clicks):
        if not _trading_app:
            raise dash.exceptions.PreventUpdate

        ctx = callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
        try:
            btn_id = json.loads(prop_id)
            rec_id = int(btn_id.get("index"))
            action_type = btn_id.get("type")
        except Exception:
            raise dash.exceptions.PreventUpdate

        if action_type == "approve-rec":
            result = _trading_app.executor.approve_recommendation(rec_id)
            if result.get("status") in {"submitted", "queued"}:
                return f"✅ Recommendation {rec_id} approved ({result.get('status')})"
            if result.get("status") == "not_found":
                return f"Recommendation {rec_id} is no longer pending"
            return f"❌ Approve failed for recommendation {rec_id}: {result.get('error', 'unknown error')}"

        if action_type == "reject-rec":
            result = _trading_app.executor.reject_recommendation(rec_id, reason="Rejected from dashboard")
            if result.get("status") == "rejected":
                return f"Rejected recommendation {rec_id}"
            if result.get("status") == "not_found":
                return f"Recommendation {rec_id} is no longer pending"
            return f"❌ Reject failed for recommendation {rec_id}: {result.get('error', 'unknown error')}"

        raise dash.exceptions.PreventUpdate

    # ── Analysis progress + AI insights ─────────────────────
    @app.callback(
        [
            Output("analysis-progress", "value"),
            Output("analysis-progress", "animated"),
            Output("analysis-progress", "color"),
            Output("analysis-progress-label", "children"),
            Output("insights-feed", "children"),
        ],
        Input("fast-refresh", "n_intervals"),
        prevent_initial_call=False,
    )
    def refresh_analysis_status(n):
        if not _trading_app:
            idle_msg = "Waiting for trading engine..."
            return 0, False, "secondary", idle_msg, [
                html.Div([
                    html.Div("System", className="timestamp"),
                    html.Div(idle_msg, style={"color": "#94a3b8"}),
                ], className="insight-entry")
            ]

        state = getattr(_trading_app, "analysis_state", {}) or {}
        pct = int(state.get("progress_pct", 0))
        in_progress = bool(state.get("in_progress", False))
        stage = str(state.get("stage", "idle"))
        msg = str(state.get("message", "Waiting for first analysis cycle..."))

        if stage == "failed":
            color = "danger"
        elif stage == "complete":
            color = "success"
        elif in_progress:
            color = "primary"
        else:
            color = "secondary"

        # Build recent AI insights from decision logs
        entries = []
        try:
            recent = _trading_app.audit.get_recent_decisions(limit=5)
            for item in recent:
                ts = item.get("timestamp")
                ts_text = datetime.fromisoformat(ts).strftime("%H:%M:%S") if ts else "Recent"

                proposals = json.loads(item.get("trade_proposals", "[]") or "[]")
                executions = json.loads(item.get("execution_results", "[]") or "[]")
                risks = json.loads(item.get("risk_decisions", "[]") or "[]")

                queued = sum(1 for x in executions if x.get("status") == "queued")
                submitted = sum(1 for x in executions if x.get("status") == "submitted")
                rejected = sum(1 for x in executions if x.get("status") == "rejected")
                rejected_reasons = [
                    "; ".join(r.get("reasons", []))
                    for r in risks if not r.get("approved", False)
                ]
                reason_text = rejected_reasons[0] if rejected_reasons else "No blocking reasons"

                entries.append(
                    html.Div([
                        html.Div(ts_text, className="timestamp"),
                        html.Div(
                            f"Proposals: {len(proposals)} | Queued: {queued} | "
                            f"Submitted: {submitted} | Rejected: {rejected}",
                            style={"color": "#f1f5f9"},
                        ),
                        html.Div(
                            f"Top risk note: {reason_text[:140]}",
                            style={"color": "#94a3b8", "marginTop": "4px"},
                        ),
                    ], className="insight-entry")
                )
        except Exception as e:
            logger.error("Failed to refresh insights feed: %s", e)

        if not entries:
            entries = [
                html.Div([
                    html.Div("System", className="timestamp"),
                    html.Div("No analysis insights yet", style={"color": "#94a3b8"}),
                ], className="insight-entry")
            ]

        return pct, in_progress, color, msg, entries

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

    # ── Close all positions ──────────────────────────────────
    @app.callback(
        Output("action-result", "children", allow_duplicate=True),
        Input("btn-close-all", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_all_positions(n):
        if not (_trading_app and n):
            raise dash.exceptions.PreventUpdate
        try:
            open_positions = len(_trading_app.portfolio.positions)
            if open_positions == 0:
                return "No open positions to close"
            # Uses Alpaca bulk close endpoint for immediate flattening.
            _trading_app.executor._client.close_all_positions(cancel_orders=True)
            return f"Close-all requested for {open_positions} position(s)"
        except Exception as e:
            logger.error("Close all positions failed: %s", e)
            return f"❌ Close-all failed: {e}"

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


def run_dashboard(trading_app=None, port: int = 8050, debug: bool | None = None):
    """Entry point to launch the dashboard server."""
    if debug is None:
        debug = os.getenv("DASH_DEBUG", "1").lower() not in ("0", "false", "no")
    app = create_app(trading_app)
    logger.info(
        "Starting dashboard on http://localhost:%d (debug=%s, hot_reload=%s)",
        port,
        debug,
        debug,
    )
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        dev_tools_hot_reload=debug,
        use_reloader=debug,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_dashboard()
