"""
Plotly-based visualisations for the BESS Arbitrage Analyser.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


# --- Colour palette ---
MODO_BLUE = "#0057FF"
MODO_DARK = "#0A0E1A"
CHARGE_COL = "#00C2FF"
DISCHARGE_COL = "#FF6B35"
SOC_COL = "#A8FF78"
PRICE_COL = "#FFD700"
GRID_COL = "rgba(255,255,255,0.08)"
FONT = "IBM Plex Mono"


def _base_layout(**kwargs) -> dict:
    return dict(
        paper_bgcolor=MODO_DARK,
        plot_bgcolor="#0F1423",
        font=dict(family=FONT, color="#C8D0E0", size=12),
        xaxis=dict(gridcolor=GRID_COL, zeroline=False),
        yaxis=dict(gridcolor=GRID_COL, zeroline=False),
        margin=dict(l=50, r=20, t=50, b=40),
        **kwargs,
    )


def price_heatmap(prices: pd.Series) -> go.Figure:
    """
    Hour-of-day × day-of-week price heatmap (average $/MWh).
    Reveals the structural spread available for arbitrage.
    """
    df = prices.to_frame("price").copy()
    df["hour"] = df.index.hour
    df["dow"] = df.index.day_name()

    pivot = df.pivot_table(
        values="price", index="hour", columns="dow", aggfunc="median"
    )
    # Ensure Mon–Sun order
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex(columns=[d for d in dow_order if d in pivot.columns])

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=[f"{h:02d}:00" for h in pivot.index],
            colorscale=[
                [0.0, "#0A2463"],
                [0.3, "#1E6091"],
                [0.5, "#F4A261"],
                [0.75, "#E76F51"],
                [1.0, "#FFFFFF"],
            ],
            colorbar=dict(title="$/MWh", tickfont=dict(family=FONT)),
            hovertemplate="Day: %{x}<br>Hour: %{y}<br>Price: $%{z:.1f}/MWh<extra></extra>",
        )
    )
    fig.update_layout(
        title="Median Price by Hour & Day of Week  |  Identifying Arbitrage Windows",
        **_base_layout(height=500),
    )
    return fig


def price_duration_curve(prices: pd.Series) -> go.Figure:
    """Load (price) duration curve — shows how often prices are above/below thresholds."""
    sorted_prices = np.sort(prices.values)[::-1]
    pct = np.linspace(0, 100, len(sorted_prices))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pct,
            y=sorted_prices,
            mode="lines",
            line=dict(color=PRICE_COL, width=2),
            fill="tozeroy",
            fillcolor="rgba(255,215,0,0.08)",
            hovertemplate="Top %{x:.1f}% of hours<br>Price: $%{y:.1f}/MWh<extra></extra>",
        )
    )
    # Reference lines
    for lvl, label in [(0, "$0"), (50, "$50"), (100, "$100")]:
        fig.add_hline(
            y=lvl,
            line=dict(color="rgba(255,255,255,0.3)", dash="dot", width=1),
            annotation_text=label,
            annotation_font=dict(color="rgba(255,255,255,0.5)"),
        )
    fig.update_layout(
        title="Price Duration Curve  |  Spread Available for Arbitrage",
        xaxis_title="% of Hours",
        yaxis_title="Price ($/MWh)",
        **_base_layout(height=380),
    ) 
    
    return fig


def dispatch_chart(dispatch_df: pd.DataFrame, battery_capacity: float) -> go.Figure:
    """
    Multi-panel dispatch chart:
      Panel 1 — LMP price
      Panel 2 — charge/discharge power
      Panel 3 — state of charge
    """
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.35, 0.35, 0.30],
        vertical_spacing=0.06,
        subplot_titles=("LMP Price ($/MWh)", "Dispatch (MW)", "State of Charge (MWh)"),
    )

    # --- Price ---
    fig.add_trace(
        go.Scatter(
            x=dispatch_df.index, y=dispatch_df["price"],
            mode="lines", name="LMP Price",
            line=dict(color=PRICE_COL, width=1.2),
        ),
        row=1, col=1,
    )

    # --- Charge/Discharge (stacked bars) ---
    fig.add_trace(
        go.Bar(
            x=dispatch_df.index, y=dispatch_df["charge_mw"],
            name="Charge", marker_color=CHARGE_COL,
            hovertemplate="%{x}<br>Charge: %{y:.2f} MW<extra></extra>",
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=dispatch_df.index, y=-dispatch_df["discharge_mw"],
            name="Discharge", marker_color=DISCHARGE_COL,
            hovertemplate="%{x}<br>Discharge: %{y:.2f} MW<extra></extra>",
        ),
        row=2, col=1,
    )

    # --- SoC ---
    fig.add_trace(
        go.Scatter(
            x=dispatch_df.index, y=dispatch_df["soc_mwh"],
            mode="lines", name="SoC",
            line=dict(color=SOC_COL, width=1.5),
            fill="tozeroy", fillcolor="rgba(168,255,120,0.08)",
        ),
        row=3, col=1,
    )
    # SoC limits
    for val, label in [
        (battery_capacity * 0.1, "SoC min"), (battery_capacity * 0.9, "SoC max")
    ]:
        fig.add_hline(
            y=val, row=3, col=1,
            line=dict(color="rgba(255,255,255,0.3)", dash="dot", width=1),
        )

    fig.update_layout(
        barmode="relative",
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            font=dict(family=FONT, size=11),
        ),
        **_base_layout(height=650),
    )
    return fig


def cumulative_revenue_chart(dispatch_df: pd.DataFrame) -> go.Figure:
    """Cumulative revenue over the analysis period with daily bars."""
    daily_rev = dispatch_df["revenue_hourly"].resample("D").sum()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.08,
        subplot_titles=("Cumulative Revenue ($)", "Daily Revenue ($)"),
    )

    fig.add_trace(
        go.Scatter(
            x=dispatch_df.index,
            y=dispatch_df["revenue_cumulative"],
            mode="lines",
            name="Cumulative Revenue",
            line=dict(color=MODO_BLUE, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0,87,255,0.12)",
        ),
        row=1, col=1,
    )

    bar_colors = [DISCHARGE_COL if v < 0 else "#2ECC71" for v in daily_rev.values]
    fig.add_trace(
        go.Bar(
            x=daily_rev.index, y=daily_rev.values,
            name="Daily Revenue",
            marker_color=bar_colors,
        ),
        row=2, col=1,
    )

    fig.update_layout(
        showlegend=False,
        **_base_layout(height=480),
    )
    return fig


def monthly_revenue_bar(dispatch_df: pd.DataFrame) -> go.Figure:
    """Monthly revenue breakdown."""
    monthly = dispatch_df["revenue_hourly"].resample("ME").sum().reset_index()
    monthly.columns = ["month", "revenue"]
    monthly["month_label"] = monthly["month"].dt.strftime("%b %Y")

    fig = go.Figure(
        go.Bar(
            x=monthly["month_label"],
            y=monthly["revenue"],
            marker_color=[
                DISCHARGE_COL if v < 0 else MODO_BLUE for v in monthly["revenue"]
            ],
            text=[f"${v:,.0f}" for v in monthly["revenue"]],
            textposition="outside",
            textfont=dict(family=FONT, size=11),
            hovertemplate="%{x}<br>Revenue: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Monthly Arbitrage Revenue",
        yaxis_title="Revenue ($)",
        **_base_layout(height=380),
    )
    return fig


def hourly_avg_dispatch(dispatch_df: pd.DataFrame) -> go.Figure:
    """Average charge/discharge profile by hour of day — reveals strategy pattern."""
    hourly = dispatch_df.groupby(dispatch_df.index.hour)[
        ["charge_mw", "discharge_mw"]
    ].mean()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=hourly.index, y=hourly["charge_mw"], name="Avg Charge",
               marker_color=CHARGE_COL)
    )
    fig.add_trace(
        go.Bar(x=hourly.index, y=-hourly["discharge_mw"], name="Avg Discharge",
               marker_color=DISCHARGE_COL)
    )
    fig.update_layout(
        barmode="relative",
        title="Average Dispatch Profile by Hour of Day",
        yaxis_title="Power (MW)",
        **_base_layout(height=350),
    )
    fig.update_xaxes(title="Hour", tickmode="linear", tick0=0, dtick=2)
    return fig