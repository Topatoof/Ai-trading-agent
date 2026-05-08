"""
Trade History Layout — Tab 3
"""
from dash import html, dcc, dash_table
import plotly.graph_objects as go


def create_history_layout():
    return html.Div([
        html.Div([
            _mc("hist-total-trades", "Total Trades", "0", "blue"),
            _mc("hist-win-rate", "Win Rate", "—", "green"),
            _mc("hist-realized-pnl", "Realized P&L", "$0.00", "purple"),
            _mc("hist-avg-wl", "Avg Win/Loss", "—", "blue"),
        ], className="metrics-grid"),

        html.Div([
            html.Div("Cumulative P&L", className="section-title"),
            dcc.Graph(id="cumulative-pnl-chart", config={"displayModeBar": False},
                      style={"height": "300px"}, figure=_empty()),
        ], className="glass-card", style={"marginBottom": "24px"}),

        html.Div([
            html.Div("Trade Log", className="section-title"),
            dash_table.DataTable(
                id="trade-log-table",
                columns=[
                    {"name": "Time", "id": "timestamp"},
                    {"name": "Symbol", "id": "symbol"},
                    {"name": "Side", "id": "side"},
                    {"name": "Qty", "id": "qty", "type": "numeric"},
                    {"name": "Price", "id": "price", "type": "numeric"},
                    {"name": "Mode", "id": "mode"},
                    {"name": "Status", "id": "status"},
                    {"name": "Confidence", "id": "confidence", "type": "numeric"},
                    {"name": "P&L", "id": "pnl", "type": "numeric"},
                    {"name": "Reasoning", "id": "reasoning"},
                ],
                data=[],
                style_header={"backgroundColor": "rgba(255,255,255,0.03)", "color": "#94a3b8",
                              "fontWeight": "600", "fontSize": "11px", "border": "none",
                              "borderBottom": "1px solid rgba(255,255,255,0.06)"},
                style_cell={"backgroundColor": "transparent", "color": "#f1f5f9",
                            "fontSize": "13px", "fontFamily": "'Inter', sans-serif",
                            "border": "none", "borderBottom": "1px solid rgba(255,255,255,0.04)",
                            "padding": "10px 14px", "maxWidth": "200px", "overflow": "hidden",
                            "textOverflow": "ellipsis"},
                style_data_conditional=[
                    {"if": {"filter_query": "{side} = BUY"}, "color": "#10b981"},
                    {"if": {"filter_query": "{side} = SELL"}, "color": "#ef4444"},
                    {"if": {"filter_query": "{pnl} > 0", "column_id": "pnl"}, "color": "#10b981"},
                    {"if": {"filter_query": "{pnl} < 0", "column_id": "pnl"}, "color": "#ef4444"},
                ],
                page_size=25, sort_action="native", filter_action="native",
            ),
        ], className="glass-card"),
    ])


def _mc(id_, label, value, color):
    return html.Div([
        html.Div(label, className="metric-label"),
        html.Div(value, id=id_, className="metric-value neutral"),
    ], className=f"metric-card {color}")


def _empty():
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=16, r=16, t=16, b=16),
                      xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)"),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickprefix="$"),
                      font=dict(family="Inter", color="#94a3b8"),
                      annotations=[dict(text="No trades yet", xref="paper", yref="paper",
                                        x=0.5, y=0.5, font=dict(size=14, color="#64748b"), showarrow=False)])
    return fig
