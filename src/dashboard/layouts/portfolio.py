"""
Portfolio Overview Layout — Tab 1
"""

from __future__ import annotations

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go


def create_portfolio_layout():
    """Build the Portfolio Overview tab layout."""
    return html.Div([
        # ── Top Metrics Row ──────────────────────────────────
        html.Div([
            _metric_card("total-equity", "Total Equity", "$0.00", "blue"),
            _metric_card("daily-pnl", "Daily P&L", "$0.00", "green"),
            _metric_card("total-pnl", "Total P&L", "$0.00", "purple"),
            _metric_card("cash-available", "Cash Available", "$0.00", "blue"),
            _metric_card("open-positions", "Open Positions", "0", "purple"),
            _metric_card("drawdown", "Drawdown", "0.00%", "red"),
        ], className="metrics-grid"),

        # ── Charts Row ───────────────────────────────────────
        html.Div([
            # Equity curve
            html.Div([
                html.Div("Equity Curve", className="section-title"),
                dcc.Graph(
                    id="equity-curve-chart",
                    config={"displayModeBar": False},
                    style={"height": "320px"},
                    figure=_empty_chart("Portfolio value over time"),
                ),
            ], className="glass-card", style={"flex": "2"}),

            # Asset allocation
            html.Div([
                html.Div("Asset Allocation", className="section-title"),
                dcc.Graph(
                    id="allocation-chart",
                    config={"displayModeBar": False},
                    style={"height": "320px"},
                    figure=_empty_pie_chart(),
                ),
            ], className="glass-card", style={"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "marginBottom": "24px"}),

        # ── Positions Table ──────────────────────────────────
        html.Div([
            html.Div("Open Positions", className="section-title"),
            dash_table.DataTable(
                id="positions-table",
                columns=[
                    {"name": "Symbol", "id": "symbol"},
                    {"name": "Qty", "id": "qty", "type": "numeric"},
                    {"name": "Avg Entry", "id": "avg_entry", "type": "numeric",
                     "format": {"specifier": "$.2f"}},
                    {"name": "Current", "id": "current", "type": "numeric",
                     "format": {"specifier": "$.2f"}},
                    {"name": "Mkt Value", "id": "market_value", "type": "numeric",
                     "format": {"specifier": "$,.2f"}},
                    {"name": "P&L", "id": "pnl", "type": "numeric",
                     "format": {"specifier": "$,.2f"}},
                    {"name": "P&L %", "id": "pnl_pct", "type": "numeric",
                     "format": {"specifier": "+.2%"}},
                ],
                data=[],
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": "rgba(255,255,255,0.03)",
                    "color": "#94a3b8",
                    "fontWeight": "600",
                    "fontSize": "11px",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.5px",
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
                    "padding": "12px 16px",
                    "textAlign": "right",
                },
                style_cell_conditional=[
                    {"if": {"column_id": "symbol"}, "textAlign": "left", "fontWeight": "600"},
                ],
                style_data_conditional=[
                    {
                        "if": {"filter_query": "{pnl} > 0", "column_id": "pnl"},
                        "color": "#10b981",
                    },
                    {
                        "if": {"filter_query": "{pnl} < 0", "column_id": "pnl"},
                        "color": "#ef4444",
                    },
                    {
                        "if": {"filter_query": "{pnl_pct} > 0", "column_id": "pnl_pct"},
                        "color": "#10b981",
                    },
                    {
                        "if": {"filter_query": "{pnl_pct} < 0", "column_id": "pnl_pct"},
                        "color": "#ef4444",
                    },
                ],
                page_size=20,
                sort_action="native",
            ),
        ], className="glass-card"),

    ])


def _metric_card(id_: str, label: str, value: str, color: str = "blue"):
    """Create a single metric card."""
    return html.Div([
        html.Div(label, className="metric-label"),
        html.Div(value, id=id_, className=f"metric-value neutral"),
    ], className=f"metric-card {color}")


def _empty_chart(title: str) -> go.Figure:
    """Create an empty placeholder chart."""
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=16, t=16, b=16),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.04)",
            zerolinecolor="rgba(255,255,255,0.06)",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.04)",
            zerolinecolor="rgba(255,255,255,0.06)",
        ),
        font=dict(family="Inter", color="#94a3b8"),
        annotations=[dict(
            text=title,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            font=dict(size=14, color="#64748b"),
            showarrow=False,
        )],
    )
    return fig


def _empty_pie_chart() -> go.Figure:
    """Create an empty placeholder pie chart."""
    fig = go.Figure(data=[go.Pie(
        labels=["Cash"],
        values=[100],
        marker=dict(colors=["rgba(59,130,246,0.3)"]),
        hole=0.65,
        textinfo="label",
        textfont=dict(color="#94a3b8", size=12),
    )])
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=16, t=16, b=16),
        showlegend=False,
        font=dict(family="Inter"),
    )
    return fig
