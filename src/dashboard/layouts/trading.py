"""
Active Trading Layout — Tab 2
"""

from __future__ import annotations

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc


def create_trading_layout():
    """Build the Active Trading tab layout."""
    return html.Div([
        # ── Top Bar: Mode + Circuit Breaker ──────────────────
        html.Div([
            # Mode toggle
            html.Div([
                html.Div("Trading Mode", className="section-title"),
                html.Div([
                    html.Button(
                        "Advisory",
                        id="btn-advisory",
                        className="mode-btn active",
                        n_clicks=0,
                    ),
                    html.Button(
                        "Autonomous",
                        id="btn-autonomous",
                        className="mode-btn",
                        n_clicks=0,
                    ),
                ], className="mode-toggle"),
                html.Div(
                    id="mode-status",
                    style={"marginTop": "12px", "fontSize": "13px", "color": "#94a3b8"},
                    children="Advisory mode — AI recommends, you approve",
                ),
            ], className="glass-card", style={"flex": "1"}),

            # Circuit breaker
            html.Div([
                html.Div("Circuit Breaker", className="section-title"),
                html.Div(
                    "● NORMAL",
                    id="circuit-status",
                    className="circuit-indicator circuit-normal",
                ),
                html.Div([
                    html.Div(id="daily-dd-display", children="Daily DD: 0.00%",
                             style={"fontSize": "13px", "color": "#94a3b8", "marginTop": "8px"}),
                    html.Div(id="total-dd-display", children="Total DD: 0.00%",
                             style={"fontSize": "13px", "color": "#94a3b8", "marginTop": "4px"}),
                ]),
                html.Button(
                    "Reset Circuit Breaker",
                    id="btn-reset-circuit",
                    className="btn-primary",
                    n_clicks=0,
                    style={"marginTop": "12px", "width": "100%"},
                ),
            ], className="glass-card", style={"flex": "1"}),

            # Quick actions
            html.Div([
                html.Div("Quick Actions", className="section-title"),
                html.Button(
                    "▶ Run Analysis Now",
                    id="btn-run-analysis",
                    className="btn-primary",
                    n_clicks=0,
                    style={"width": "100%", "marginBottom": "8px"},
                ),
                html.Button(
                    "🔄 Sync Portfolio",
                    id="btn-sync-portfolio",
                    className="btn-primary",
                    n_clicks=0,
                    style={"width": "100%", "marginBottom": "8px"},
                ),
                html.Button(
                    "⛔ Close All Positions",
                    id="btn-close-all",
                    className="btn-primary btn-danger",
                    n_clicks=0,
                    style={"width": "100%"},
                ),
            ], className="glass-card", style={"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "marginBottom": "24px"}),

        # ── Two Column: Insights + Recommendations ───────────
        html.Div([
            # AI Insights Feed
            html.Div([
                html.Div("AI Insights", className="section-title"),
                html.Div(
                    id="insights-feed",
                    className="insights-feed",
                    children=[
                        html.Div([
                            html.Div("System ready", className="timestamp"),
                            html.Div("Waiting for first analysis cycle...",
                                     style={"color": "#94a3b8"}),
                        ], className="insight-entry"),
                    ],
                ),
            ], className="glass-card", style={"flex": "1"}),

            # Pending Recommendations
            html.Div([
                html.Div("Pending Recommendations", className="section-title"),
                html.Div(
                    id="recommendations-list",
                    children=[
                        html.Div(
                            "No pending recommendations",
                            style={
                                "textAlign": "center",
                                "color": "#64748b",
                                "padding": "40px",
                                "fontSize": "14px",
                            },
                        ),
                    ],
                ),
            ], className="glass-card", style={"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "marginBottom": "24px"}),

        # ── Active Orders ────────────────────────────────────
        html.Div([
            html.Div("Active Orders", className="section-title"),
            dash_table.DataTable(
                id="active-orders-table",
                columns=[
                    {"name": "Time", "id": "time"},
                    {"name": "Symbol", "id": "symbol"},
                    {"name": "Side", "id": "side"},
                    {"name": "Qty", "id": "qty"},
                    {"name": "Type", "id": "type"},
                    {"name": "Status", "id": "status"},
                ],
                data=[],
                style_header={
                    "backgroundColor": "rgba(255,255,255,0.03)",
                    "color": "#94a3b8",
                    "fontWeight": "600",
                    "fontSize": "11px",
                    "textTransform": "uppercase",
                    "border": "none",
                    "borderBottom": "1px solid rgba(255,255,255,0.06)",
                },
                style_cell={
                    "backgroundColor": "transparent",
                    "color": "#f1f5f9",
                    "fontSize": "13px",
                    "fontFamily": "'Inter', sans-serif",
                    "border": "none",
                    "borderBottom": "1px solid rgba(255,255,255,0.04)",
                    "padding": "10px 14px",
                },
                style_data_conditional=[
                    {
                        "if": {"filter_query": "{side} = BUY"},
                        "color": "#10b981",
                    },
                    {
                        "if": {"filter_query": "{side} = SELL"},
                        "color": "#ef4444",
                    },
                ],
                page_size=10,
            ),
        ], className="glass-card"),

        # Mode state store
        dcc.Store(id="current-mode", data="advisory"),
        # Status banner — shows feedback from button actions
        html.Div(
            id="action-result",
            style={
                "padding": "12px 20px",
                "borderRadius": "8px",
                "background": "rgba(59,130,246,0.1)",
                "border": "1px solid rgba(59,130,246,0.2)",
                "color": "#94a3b8",
                "fontSize": "13px",
                "marginTop": "16px",
                "textAlign": "center",
            },
            children="Ready — click 'Run Analysis Now' to start",
        ),
    ])
