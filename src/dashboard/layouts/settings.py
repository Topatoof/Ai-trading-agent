"""
Settings & Logs Layout — Tab 5
"""
from dash import html, dcc, dash_table


def create_settings_layout():
    return html.Div([
        html.Div([
            # System Health
            html.Div([
                html.Div("System Health", className="section-title"),
                html.Div(id="health-indicators", children=[
                    _health_row("Alpaca API", "checking", "alpaca-health"),
                    _health_row("LM Studio", "checking", "llm-health"),
                    _health_row("Database", "checking", "db-health"),
                    _health_row("Scheduler", "checking", "scheduler-health"),
                ]),
            ], className="glass-card", style={"flex": "1"}),

            # Risk Parameters
            html.Div([
                html.Div("Risk Parameters", className="section-title"),
                _param_row("Max Position %", "risk-max-pos", 10),
                _param_row("Max Positions", "risk-max-count", 15),
                _param_row("Trailing Stop %", "risk-trail-stop", 3),
                _param_row("Daily DD Halt %", "risk-daily-dd", 5),
                _param_row("Total DD Halt %", "risk-total-dd", 15),
                _param_row("Min Confidence", "risk-min-conf", 0.6),
                html.Button("Save Risk Settings", id="btn-save-risk",
                            className="btn-primary", n_clicks=0,
                            style={"width": "100%", "marginTop": "16px"}),
                html.Div(id="risk-save-status", style={"marginTop": "8px", "color": "#94a3b8", "fontSize": "12px"}),
            ], className="glass-card", style={"flex": "1"}),

            # Asset Universe
            html.Div([
                html.Div("Asset Universe", className="section-title"),
                html.Div(id="universe-count", children="50 symbols",
                         style={"color": "#94a3b8", "fontSize": "13px", "marginBottom": "12px"}),
                dcc.Textarea(id="universe-textarea",
                             style={"width": "100%", "height": "200px", "padding": "12px",
                                    "borderRadius": "8px", "border": "1px solid rgba(255,255,255,0.1)",
                                    "background": "#111827", "color": "#f1f5f9", "fontFamily": "JetBrains Mono",
                                    "fontSize": "12px", "resize": "vertical"}),
            ], className="glass-card", style={"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "marginBottom": "24px"}),

        # Audit Log Viewer
        html.Div([
            html.Div("Decision Audit Log", className="section-title"),
            dash_table.DataTable(
                id="audit-log-table",
                columns=[
                    {"name": "Time", "id": "timestamp"},
                    {"name": "Market State", "id": "market_state"},
                    {"name": "Proposals", "id": "trade_proposals"},
                    {"name": "Risk", "id": "risk_decisions"},
                    {"name": "Results", "id": "execution_results"},
                ],
                data=[],
                style_header={"backgroundColor": "rgba(255,255,255,0.03)", "color": "#94a3b8",
                              "fontWeight": "600", "fontSize": "11px", "border": "none",
                              "borderBottom": "1px solid rgba(255,255,255,0.06)"},
                style_cell={"backgroundColor": "transparent", "color": "#f1f5f9",
                            "fontSize": "12px", "fontFamily": "'JetBrains Mono', monospace",
                            "border": "none", "borderBottom": "1px solid rgba(255,255,255,0.04)",
                            "padding": "8px 12px", "maxWidth": "300px", "overflow": "hidden",
                            "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                page_size=20, sort_action="native",
            ),
        ], className="glass-card"),
    ])


def _health_row(label, status, id_):
    return html.Div([
        html.Span("●", id=f"{id_}-dot",
                   style={"color": "#64748b", "marginRight": "8px", "fontSize": "10px"}),
        html.Span(label, style={"color": "#f1f5f9", "fontSize": "13px", "flex": "1"}),
        html.Span(status, id=id_,
                   style={"color": "#64748b", "fontSize": "12px", "fontFamily": "JetBrains Mono"}),
    ], style={"display": "flex", "alignItems": "center", "padding": "10px 0",
              "borderBottom": "1px solid rgba(255,255,255,0.04)"})


def _param_row(label, id_, default):
    return html.Div([
        html.Label(label, style={"color": "#94a3b8", "fontSize": "12px", "flex": "1"}),
        dcc.Input(id=id_, type="number", value=default,
                  style={"width": "80px", "padding": "6px 10px", "borderRadius": "6px",
                         "border": "1px solid rgba(255,255,255,0.1)", "background": "#0a0e1a",
                         "color": "#f1f5f9", "fontSize": "13px", "textAlign": "right"}),
    ], style={"display": "flex", "alignItems": "center", "padding": "8px 0",
              "borderBottom": "1px solid rgba(255,255,255,0.04)"})
