"""
Backtesting Layout — Tab 4
"""
from dash import html, dcc
import plotly.graph_objects as go


def create_backtest_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div("Backtest Configuration", className="section-title"),
                html.Div([
                    html.Label("Date Range", style={"color": "#94a3b8", "fontSize": "12px", "marginBottom": "4px"}),
                    dcc.DatePickerRange(id="bt-date-range", style={"marginBottom": "16px"}),
                ]),
                html.Div([
                    html.Label("Initial Capital ($)", style={"color": "#94a3b8", "fontSize": "12px"}),
                    dcc.Input(id="bt-capital", type="number", value=100000,
                              style={"width": "100%", "padding": "8px 12px", "borderRadius": "6px",
                                     "border": "1px solid rgba(255,255,255,0.1)", "background": "#111827",
                                     "color": "#f1f5f9", "marginBottom": "16px"}),
                ]),
                html.Div([
                    html.Label("Min Signal Score", style={"color": "#94a3b8", "fontSize": "12px"}),
                    dcc.Slider(id="bt-signal-score", min=0.1, max=0.8, step=0.05, value=0.3,
                               marks={0.1: "0.1", 0.3: "0.3", 0.5: "0.5", 0.8: "0.8"},
                               tooltip={"placement": "bottom"}),
                ], style={"marginBottom": "16px"}),
                html.Button("▶ Run Backtest", id="btn-run-backtest", className="btn-primary btn-success",
                            n_clicks=0, style={"width": "100%", "marginTop": "8px"}),
                html.Div(id="bt-status", style={"marginTop": "12px", "color": "#94a3b8", "fontSize": "13px"}),
            ], className="glass-card", style={"flex": "1"}),

            html.Div([
                html.Div("Backtest Results", className="section-title"),
                html.Div(id="bt-metrics", children=[
                    _bt_metric("Return", "—", "bt-return"),
                    _bt_metric("Sharpe", "—", "bt-sharpe"),
                    _bt_metric("Sortino", "—", "bt-sortino"),
                    _bt_metric("Max DD", "—", "bt-maxdd"),
                    _bt_metric("Win Rate", "—", "bt-winrate"),
                    _bt_metric("Profit Factor", "—", "bt-pf"),
                    _bt_metric("Total Trades", "—", "bt-trades"),
                ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"}),
            ], className="glass-card", style={"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "marginBottom": "24px"}),

        html.Div([
            html.Div("Equity Curve (Backtest)", className="section-title"),
            dcc.Graph(id="bt-equity-chart", config={"displayModeBar": False},
                      style={"height": "350px"}, figure=_empty_bt()),
        ], className="glass-card"),

        dcc.Store(id="bt-results-store", data=None),
    ])


def _bt_metric(label, value, id_):
    return html.Div([
        html.Div(label, style={"fontSize": "11px", "color": "#64748b", "textTransform": "uppercase",
                               "letterSpacing": "0.5px", "marginBottom": "4px"}),
        html.Div(value, id=id_, style={"fontSize": "20px", "fontWeight": "700", "color": "#f1f5f9"}),
    ], style={"padding": "12px", "background": "rgba(255,255,255,0.02)", "borderRadius": "8px"})


def _empty_bt():
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=16, r=16, t=16, b=16),
                      xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)"),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickprefix="$"),
                      font=dict(family="Inter", color="#94a3b8"),
                      annotations=[dict(text="Run a backtest to see results", xref="paper", yref="paper",
                                        x=0.5, y=0.5, font=dict(size=14, color="#64748b"), showarrow=False)])
    return fig
