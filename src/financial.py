"""
financial.py — BESS Project Financial Analysis
================================================
Computes LCOS and Payback Period for a BESS arbitrage project.
"""

import numpy as np
import pandas as pd


def compute_lcos(
    capex_per_kwh: float,        # $/kWh — total installed cost
    power_mw: float,             # MW
    capacity_mwh: float,         # MWh
    annual_revenue: float,       # $/year from arbitrage
    project_life_years: int = 15,
    wacc: float = 0.08,          # weighted average cost of capital
    opex_pct_capex: float = 0.01, # annual O&M as % of CAPEX
    degradation_pct_year: float = 0.02,  # capacity loss per year
    annual_cycles: float = 365.0,
) -> dict:
    """
    Compute LCOS (Levelized Cost of Storage) and project financials.
    
    LCOS = (CAPEX + NPV of OPEX) / NPV of total discharged energy
    
    Returns dict with all financial metrics.
    """
    # ── CAPEX ──────────────────────────────────────────────
    capex_total = capex_per_kwh * capacity_mwh * 1000  # convert MWh → kWh

    # ── Annual costs and revenues ──────────────────────────
    opex_annual = opex_pct_capex * capex_total

    # ── Discounted cash flows ──────────────────────────────
    years = np.arange(1, project_life_years + 1)
    discount_factors = 1 / (1 + wacc) ** years

    # Degradation: capacity shrinks each year
    capacity_factors = (1 - degradation_pct_year) ** (years - 1)

    # Revenue degrades with capacity
    revenues = annual_revenue * capacity_factors
    opex = np.full(project_life_years, opex_annual)

    # Net cash flows (after OPEX)
    net_cf = revenues - opex

    # Discounted values
    pv_revenues = revenues * discount_factors
    pv_opex = opex * discount_factors
    pv_net_cf = net_cf * discount_factors

    # ── NPV ────────────────────────────────────────────────
    npv = -capex_total + np.sum(pv_net_cf)

    # ── Payback period (undiscounted) ──────────────────────
    cumulative_cf = np.cumsum(net_cf) - capex_total
    payback_years = None
    for i, cf in enumerate(cumulative_cf):
        if cf >= 0:
            # Interpolate exact payback
            if i == 0:
                payback_years = capex_total / net_cf[0]
            else:
                prev = cumulative_cf[i - 1]
                payback_years = (i) + abs(prev) / net_cf[i]
            break

    # ── LCOS ───────────────────────────────────────────────
    # Total discharged energy per year (MWh), degraded over time
    mwh_discharged_annual = capacity_mwh * annual_cycles * capacity_factors
    pv_mwh_discharged = mwh_discharged_annual * discount_factors

    lcos = (capex_total + np.sum(pv_opex)) / np.sum(pv_mwh_discharged)

    # ── Annual cash flow table ─────────────────────────────
    cf_table = pd.DataFrame({
        "Year": years,
        "Revenue ($)": revenues,
        "OPEX ($)": opex,
        "Net CF ($)": net_cf,
        "Cumulative CF ($)": np.cumsum(net_cf) - capex_total,
        "Capacity Factor": capacity_factors,
    })

    return {
        "capex_total": capex_total,
        "opex_annual": opex_annual,
        "npv": npv,
        "payback_years": payback_years,
        "lcos": lcos,
        "annual_revenue": annual_revenue,
        "cf_table": cf_table,
        "project_life_years": project_life_years,
        "wacc": wacc,
    }
