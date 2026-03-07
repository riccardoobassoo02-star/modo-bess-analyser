"""
BESS Arbitrage Analyser  ·  Modo Energy Take-Home Task
=======================================================

Answers the question:
    "How much revenue can a battery storage asset earn from
     day-ahead energy arbitrage in ERCOT, and what drives that revenue?"

Author: Riccardo Morandi
"""

import streamlit as st
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.data_loader import load_ercot_dam_prices, summarize_prices, ERCOT_HUBS
from src.optimizer import BatteryParams, rolling_daily_dispatch, compute_revenue_stats
from src.viz import (
    price_heatmap,
    price_duration_curve,
    dispatch_chart,
    cumulative_revenue_chart,
    monthly_revenue_bar,
    hourly_avg_dispatch,
)

# ─────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="BESS Arbitrage Analyser · ERCOT",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
    h1, h2, h3 { font-family: 'Syne', sans-serif !important; font-weight: 700; }
    .metric-label { font-size: 0.78rem; color: #8892A0; text-transform: uppercase; letter-spacing: 0.08em; }
    .metric-value { font-size: 1.6rem; font-weight: 600; color: #E0E8FF; }
    .stMetric label { font-family: 'Space Grotesk', sans-serif !important; font-weight: 500; }
    div[data-testid="stMetricValue"] { font-family: 'Syne', sans-serif; font-size: 1.5rem; font-weight: 700; }
    .sidebar-section { color: #8892A0; font-size: 0.72rem; text-transform: uppercase;
                       letter-spacing: 0.12em; margin-top: 1rem; margin-bottom: 0.3rem;
                       font-family: 'Space Grotesk', sans-serif; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
#  Sidebar — configuration
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ BESS Arbitrage Analyser")
    st.markdown("*ERCOT Day-Ahead Market*")
    st.divider()

    st.markdown('<div class="sidebar-section">Market Settings</div>', unsafe_allow_html=True)
    data_source = st.radio(
    "Data Source",
    ["Real ERCOT 2023", "Synthetic"],
    index=0,
    )
    hub = st.selectbox("ERCOT Hub", ERCOT_HUBS, index=0)
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start", value=pd.Timestamp("2023-01-01"))
    with col2:
        end_date = st.date_input("End", value=pd.Timestamp("2023-12-31"))

    st.markdown('<div class="sidebar-section">Battery Specifications</div>', unsafe_allow_html=True)
    power_mw = st.slider("Power (MW)", 0.5, 10.0, 1.0, 0.5)
    duration_h = st.slider("Duration (hours)", 1, 8, 2, 1)
    capacity_mwh = power_mw * duration_h
    st.caption(f"Capacity: **{capacity_mwh:.1f} MWh**")

    rt_efficiency = st.slider("Round-trip efficiency (%)", 70, 97, 85, 1) / 100
    soc_min = st.slider("Min SoC (%)", 0, 30, 0, 5) / 100
    soc_max = st.slider("Max SoC (%)", 70, 100, 90, 5) / 100

    st.markdown('<div class="sidebar-section">Analysis Mode</div>', unsafe_allow_html=True)
    rolling = st.toggle(
        "Day-ahead rolling dispatch",
        value=True,
        help="Optimise day by day (realistic). Off = perfect foresight over full period.",
    )

    run_btn = st.button("▶  Run Analysis", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
#  Header
# ─────────────────────────────────────────────
st.markdown(
    f"""
    <h1 style='font-family: IBM Plex Mono; color: #E0E8FF; margin-bottom: 0;'>
        Battery Arbitrage Revenue Analyser
    </h1>
    <p style='color: #8892A0; font-size: 0.9rem; margin-top: 0.3rem;'>
        ERCOT Day-Ahead Market · {hub} · {power_mw} MW / {capacity_mwh:.0f} MWh BESS
    </p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ─────────────────────────────────────────────
#  Session state to persist results
# ─────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None

# ─────────────────────────────────────────────
#  Main logic: load data → optimise → display
# ─────────────────────────────────────────────
if run_btn or st.session_state.results is None:
    battery = BatteryParams(
    power_mw=power_mw,
    capacity_mwh=capacity_mwh,
    efficiency_rt=rt_efficiency,
    soc_min_pct=soc_min,
    soc_max_pct=soc_max,
)

    with st.spinner("Loading ERCOT prices…"):
        try:
            if data_source == "Real ERCOT 2023":
                from src.data_loader import load_ercot_real_data
                prices = load_ercot_real_data(
                    "data/rpt.00013060.0000000000000000.DAMLZHBSPP_2023.xlsx",
                    hub=hub
                )
                prices = prices.loc[str(start_date):str(end_date)]
                prices["hub"] = hub
            else:
                prices = load_ercot_dam_prices(
                    str(start_date), str(end_date), hub=hub
                ) 
        except Exception as e:
            st.error(f"Dat load failed: {e}")
            st.stop() 

    with st.spinner("Optimising dispatch…"):
        try:
            if rolling:
                dispatch_df = rolling_daily_dispatch(prices["price"], battery=battery)
            else:
                from src.optimizer import optimise_dispatch
                res = optimise_dispatch(prices["price"], battery=battery)
                dispatch_df = res.to_dataframe()
        except Exception as e:
            st.error(f"Optimisation failed: {e}")
            st.stop()

    stats = compute_revenue_stats(dispatch_df, battery)
    price_stats = summarize_prices(prices)

    st.session_state.results = {
        "prices": prices,
        "dispatch_df": dispatch_df,
        "stats": stats,
        "price_stats": price_stats,
        "battery": battery,
        "hub": hub,
        "rolling": rolling,
    }

# ─────────────────────────────────────────────
#  Display results
# ─────────────────────────────────────────────
if st.session_state.results:
    r = st.session_state.results
    dispatch_df = r["dispatch_df"]
    prices = r["prices"]
    stats = r["stats"]
    price_stats = r["price_stats"]
    battery = r["battery"]

    # ── KPI row ──────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Revenue", f"${stats['total_revenue_usd']:,.0f}")
    k2.metric("Avg Daily Revenue", f"${stats['avg_daily_revenue_usd']:,.0f}")
    k3.metric("Revenue / MWh Capacity", f"${stats['revenue_per_mwh_capacity']:,.0f}")
    k4.metric("Total Cycles", f"{stats['total_cycles']:.1f}")
    k5.metric("Avg Price", f"${price_stats['mean']:.1f}/MWh")

    st.divider()

    # ── Tabs ─────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊  Market Overview", "⚡  Dispatch & SoC", "💰  Revenue Analysis", "💼  Financial Analysis"]
    )

    with tab1:
        st.markdown("### Price Structure")
        st.markdown(
            """
            Understanding the *shape* of prices is the first step in sizing a BESS opportunity.
            The heatmap reveals which hours/days offer the widest spreads —
            the primary driver of arbitrage revenue.
            """
        )
        st.plotly_chart(price_heatmap(prices["price"]), use_container_width=True)

        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(
                price_duration_curve(prices["price"]), use_container_width=True
            )
        with col_r:
            # Price stats table
            st.markdown("**Price Statistics**")
            ps = price_stats
            stats_md = f"""
| Metric | Value |
|--------|-------|
| Mean | ${ps['mean']:.1f}/MWh |
| Median | ${ps['median']:.1f}/MWh |
| Std Dev | ${ps['std']:.1f}/MWh |
| 5th percentile | ${ps['p5']:.1f}/MWh |
| 95th percentile | ${ps['p95']:.1f}/MWh |
| Max | ${ps['max']:.1f}/MWh |
| % hours negative | {ps['pct_negative']:.1f}% |
| % hours > $100 | {ps['pct_above_100']:.1f}% |
"""
            st.markdown(stats_md)

            st.markdown("---")
            st.markdown(
                """
                **Key insight for BESS sizing**

                The **price spread** (P95 − P5) is the theoretical maximum 
                daily arbitrage value. A real BESS captures a fraction of this,
                constrained by capacity and round-trip losses.
                Negative prices and scarcity spikes both boost revenue and
                ERCOT's market design creates both regularly.
                """
            )

    with tab2:
        n_days_show = st.slider(
            "Days to display", 1, min(90, stats["n_days"]), min(14, stats["n_days"])
        )
        df_show = dispatch_df.iloc[: n_days_show * 24]

        st.plotly_chart(
            dispatch_chart(df_show, battery.capacity_mwh), use_container_width=True
        )
        st.plotly_chart(
            hourly_avg_dispatch(dispatch_df), use_container_width=True
        )

        st.markdown(
            """
            **Reading the dispatch chart**

            - 🔵 *Charge* (blue bars up) — battery buys cheap off-peak energy
            - 🟠 *Discharge* (orange bars down) — battery sells expensive peak energy
            - 🟢 *SoC* — state of charge follows the optimal fill/drain cycle

            The average profile reveals the **strategy**: typically charging
            overnight / solar hours and discharging into the evening peak.
            """
        )

    with tab3:
        st.plotly_chart(
            cumulative_revenue_chart(dispatch_df), use_container_width=True
        )
        if stats["n_days"] >= 28:
            st.plotly_chart(
                monthly_revenue_bar(dispatch_df), use_container_width=True
            ) 
    with tab4:
        st.markdown("### Project Financial Analysis")
        st.markdown("Evaluate whether the BESS project is worth building.")

        st.divider()

        # ── Inputs ──────────────────────────────────────
        col1, col2, col3 = st.columns(3)
        with col1:
            capex_per_kwh = st.number_input(
                "CAPEX ($/kWh)", min_value=50, max_value=1000,
                value=300, step=10,
                help="Typical range: $200-400/kWh for utility-scale BESS in 2024"
            )
            project_life = st.number_input(
                "Project life (years)", min_value=5, max_value=30,
                value=15, step=1
            )
        with col2:
            wacc = st.number_input(
                "WACC (%)", min_value=1.0, max_value=20.0,
                value=8.0, step=0.5,
                help="Weighted Average Cost of Capital"
            ) / 100
            opex_pct = st.number_input(
                "Annual O&M (% of CAPEX)", min_value=0.5, max_value=5.0,
                value=1.0, step=0.1
            ) / 100
        with col3:
            degradation = st.number_input(
                "Annual degradation (%)", min_value=0.0, max_value=5.0,
                value=2.0, step=0.1,
                help="Capacity loss per year"
            ) / 100
            revenue_growth = st.number_input(
                "Revenue growth (%/year)", min_value=-10.0, max_value=10.0,
                value=0.0, step=0.5,
                help="Expected annual change in arbitrage revenue"
            ) / 100

        st.divider()

        # ── Compute ──────────────────────────────────────
        from src.financial import compute_lcos

        fin = compute_lcos(
            capex_per_kwh=capex_per_kwh,
            power_mw=battery.power_mw,
            capacity_mwh=battery.capacity_mwh,
            annual_revenue=stats["avg_daily_revenue_usd"] * 365,
            project_life_years=project_life,
            wacc=wacc,
            opex_pct_capex=opex_pct,
            degradation_pct_year=degradation,
            annual_cycles=stats["avg_daily_cycles"] * 365,
        )

        # ── KPIs ─────────────────────────────────────────
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Total CAPEX", f"${fin['capex_total']:,.0f}")
        f2.metric("Annual O&M", f"${fin['opex_annual']:,.0f}")
        f3.metric(
            "Payback Period",
            f"{fin['payback_years']:.1f} years" if fin['payback_years'] else "Never",
        )
        f4.metric("LCOS", f"${fin['lcos']:.1f}/MWh")

        st.divider()

        # ── Cash flow chart ───────────────────────────────
        import plotly.graph_objects as go

        cf = fin["cf_table"]
        fig_cf = go.Figure()
        fig_cf.add_trace(go.Bar(
            x=cf["Year"], y=cf["Net CF ($)"],
            name="Annual Net CF",
            marker_color="#4A9EFF"
        ))
        fig_cf.add_trace(go.Scatter(
            x=cf["Year"], y=cf["Cumulative CF ($)"],
            name="Cumulative CF",
            line=dict(color="#FF6B35", width=2),
            yaxis="y2"
        ))
        fig_cf.add_hline(y=0, line_dash="dash", line_color="#8892A0")
        fig_cf.update_layout(
            title="Annual & Cumulative Cash Flow",
            xaxis_title="Year",
            yaxis_title="Annual Net CF ($)",
            yaxis2=dict(title="Cumulative CF ($)", overlaying="y", side="right"),
            paper_bgcolor="#0D1117",
            plot_bgcolor="#0F1423",
            font=dict(color="#C8D0E0"),
            legend=dict(x=0.01, y=0.99),
            height=400,
        )
        st.plotly_chart(fig_cf, use_container_width=True)

        # ── LCOS context ──────────────────────────────────
        avg_price = price_stats["mean"]
        spread = price_stats["p95"] - price_stats["p5"]
        st.info(
            f"""
            📌 **LCOS Interpretation**

            Your LCOS is **${fin['lcos']:.1f}/MWh** — this is the minimum average 
            price spread needed to break even over the project life.

            Current avg price spread (P95-P5): **${spread:.1f}/MWh**

            → The project is **{'viable ✅' if spread > fin['lcos'] else 'not viable at current spreads ❌'}**
            """,
        )        

        # Summary table
        st.markdown("### Summary")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(
                f"""
                **Battery:** {battery.power_mw} MW / {battery.capacity_mwh:.0f} MWh
                ({int(battery.capacity_mwh / battery.power_mw)}-hour duration)

                **Round-trip efficiency:** {battery.efficiency_rt * 100:.0f}%

                **Analysis period:** {stats['n_days']} days

                **Mode:** {'Rolling day-ahead' if r['rolling'] else 'Perfect foresight'}
                """
            )
        with col_b:
            annualised = stats["avg_daily_revenue_usd"] * 365
            st.markdown(
                f"""
                **Annualised revenue (est.):** ${annualised:,.0f}

                **Revenue/MWh capacity:** ${stats['revenue_per_mwh_capacity']:,.0f}

                **Avg daily cycles:** {stats['avg_daily_cycles']:.2f}

                **Capacity factor:** {stats['capacity_factor_pct']:.1f}%
                """
            )

        st.info(
            """
            ℹ️  **Methodology note:**  
            This tool models *energy-only arbitrage* in the ERCOT Day-Ahead Market.
            Real BESS assets can stack additional revenues from ancillary services
            (ECRS, Reg-Up/Down, Non-Spin) — often 30–60% of total revenue in ERCOT.
            This represents the conservative floor.
            """,
            icon="📌",
        )

# ─────────────────────────────────────────────
#  Footer
# ─────────────────────────────────────────────
st.divider()
st.markdown(
    """
    <p style='text-align: center; color: #4A5568; font-size: 0.75rem; font-family: IBM Plex Mono;'>
        BESS Arbitrage Analyser · Built for Modo Energy Take-Home Task · 
        Data: ERCOT MIS (gridstatus) or synthetic with realistic price dynamics
    </p>
    """,
    unsafe_allow_html=True,
)
