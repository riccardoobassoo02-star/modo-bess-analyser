"""
Battery Energy Storage System (BESS) Dispatch Optimizer.

Formulates a linear programme to maximise arbitrage revenue
from day-ahead electricity prices.

Decision variables (per timestep t):
    c[t]  : charge power   [MW], ≥ 0
    d[t]  : discharge power [MW], ≥ 0
    e[t]  : state of charge [MWh], bounded [SoC_min, SoC_max]

Objective:
    maximise  Σ_t  price[t] * (d[t] - c[t]) * Δt   [revenue in $]

Constraints:
    e[t] = e[t-1] + η_c * c[t] * Δt  -  (1/η_d) * d[t] * Δt
    0 ≤ c[t] ≤ P_max
    0 ≤ d[t] ≤ P_max
    E_min ≤ e[t] ≤ E_max
    e[0] = E_init

Note: LP relaxation of simultaneous charge/discharge constraint.
At optimum this is naturally non-binding (self-scheduling).
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from scipy.optimize import linprog


@dataclass
class BatteryParams:
    power_mw: float = 1.0          # rated charge/discharge power [MW]
    capacity_mwh: float = 2.0      # usable energy capacity [MWh]
    efficiency_rt: float = 0.85    # round-trip efficiency [fraction]
    soc_min_pct: float = 0.10      # minimum SoC as fraction of capacity
    soc_max_pct: float = 0.90      # maximum SoC as fraction of capacity
    soc_init_pct: float = 0.0     # initial SoC as fraction of capacity
    degradation_per_cycle: float = 0.0  # optional: $/cycle cost (set 0 to ignore)

    @property
    def eta_c(self) -> float:
        return self.efficiency_rt ** 0.5

    @property
    def eta_d(self) -> float:
        return self.efficiency_rt ** 0.5

    @property
    def e_min(self) -> float:
        return self.soc_min_pct * self.capacity_mwh

    @property
    def e_max(self) -> float:
        return self.soc_max_pct * self.capacity_mwh

    @property
    def e_init(self) -> float:
        return self.soc_init_pct * self.capacity_mwh


@dataclass
class DispatchResult:
    timestamps: pd.DatetimeIndex
    prices: np.ndarray          # $/MWh
    charge: np.ndarray          # MW
    discharge: np.ndarray       # MW
    soc: np.ndarray             # MWh
    revenue: np.ndarray         # cumulative $ 
    status: str                 # solver status
    total_revenue: float        # $
    total_cycles: float         # equivalent full cycles

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "price": self.prices,
                "charge_mw": self.charge,
                "discharge_mw": self.discharge,
                "net_mw": self.discharge - self.charge,
                "soc_mwh": self.soc,
                "revenue_cumulative": self.revenue,
                "revenue_hourly": np.diff(self.revenue, prepend=0),
            },
            index=self.timestamps,
        )


def optimise_dispatch(
    prices: pd.Series,
    battery: Optional[BatteryParams] = None,
    dt_h: float = 1.0,
) -> DispatchResult:
    """
    Solve the BESS arbitrage LP.

    Parameters
    ----------
    prices  : hourly price series ($/MWh), DatetimeIndex
    battery : BatteryParams (defaults to 1 MW / 2 MWh, 85% RT efficiency)
    dt_h    : timestep duration in hours (default 1.0)

    Returns
    -------
    DispatchResult with dispatch schedule and revenue breakdown
    """
    if battery is None:
        battery = BatteryParams()

    p = prices.values.astype(float)
    T = len(p)
    dt = dt_h

    # ---------- variable layout ----------
    # x = [c_0, ..., c_{T-1}, d_0, ..., d_{T-1}, e_0, ..., e_{T-1}]
    # size: 3T
    idx_c = slice(0, T)
    idx_d = slice(T, 2 * T)
    idx_e = slice(2 * T, 3 * T)
    N = 3 * T

    # ---------- objective (minimise cost → negate revenue) ----------
    # revenue = Σ price[t] * (d[t] - c[t]) * dt
    c_obj = np.zeros(N)
    c_obj[idx_c] = p * dt          # cost of charging = price * MW * h
    c_obj[idx_d] = -p * dt         # revenue from discharging

    # ---------- equality constraints (SoC dynamics) ----------
    # e[t] = e[t-1] + eta_c * c[t] * dt  -  (1/eta_d) * d[t] * dt
    # → -e[t-1] + e[t]  -  eta_c * dt * c[t]  +  (dt/eta_d) * d[t]  = 0   for t ≥ 1
    # and e[0] = e_init  → e[0] = E_init

    A_eq = np.zeros((T, N))
    b_eq = np.zeros(T)

    # e[0] = e_init
    A_eq[0, 2 * T + 0] = 1.0
    b_eq[0] = battery.e_init

    for t in range(1, T):
        A_eq[t, 2 * T + t] = 1.0           # +e[t]
        A_eq[t, 2 * T + t - 1] = -1.0      # -e[t-1]
        A_eq[t, t] = -battery.eta_c * dt   # -eta_c * c[t]
        A_eq[t, T + t] = (dt / battery.eta_d)  # +(1/eta_d)*d[t]

    # ---------- bounds ----------
    bounds = (
        [(0, battery.power_mw)] * T           # charge
        + [(0, battery.power_mw)] * T         # discharge
        + [(battery.e_min, battery.e_max)] * T  # SoC
    )

    # ---------- solve ----------
    result = linprog(
        c_obj,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
        options={"disp": False, "time_limit": 60},
    )

    if result.status not in (0, 1):
        raise RuntimeError(f"LP solver failed: {result.message}")

    x = result.x
    charge = x[idx_c]
    discharge = x[idx_d]
    soc = x[idx_e]

    # Revenue timeseries
    hourly_rev = (discharge - charge) * p * dt
    cumulative_rev = np.cumsum(hourly_rev)

    # Cycle counting (half-cycle = full charge or full discharge)
    total_cycles = np.sum(charge) * dt / battery.capacity_mwh

    return DispatchResult(
        timestamps=prices.index,
        prices=p,
        charge=charge,
        discharge=discharge,
        soc=soc,
        revenue=cumulative_rev,
        status=result.message,
        total_revenue=float(cumulative_rev[-1]),
        total_cycles=float(total_cycles),
    )


def rolling_daily_dispatch(
    prices: pd.Series, battery: Optional[BatteryParams] = None
) -> pd.DataFrame:
    """
    Optimise dispatch day-by-day (mimics realistic DAM bidding).
    Battery SoC carries over from one day to the next.
    """
    if battery is None:
        battery = BatteryParams()

    days = prices.index.normalize().unique()
    frames = []
    soc_carry = battery.e_init

    for day in days:
        day_prices = prices[prices.index.normalize() == day]
        if len(day_prices) < 1:
            continue

        # Temporarily override init SoC with carry-over
        b = BatteryParams(
            power_mw=battery.power_mw,
            capacity_mwh=battery.capacity_mwh,
            efficiency_rt=battery.efficiency_rt,
            soc_min_pct=battery.soc_min_pct,
            soc_max_pct=battery.soc_max_pct,
            soc_init_pct=soc_carry / battery.capacity_mwh,
            degradation_per_cycle=battery.degradation_per_cycle,
        )

        try:
            res = optimise_dispatch(day_prices, battery=b)
            soc_carry = res.soc[-1]
            frames.append(res.to_dataframe())
        except Exception as e:
            print(f"Optimisation failed for {day.date()}: {e}")

    if not frames:
        raise RuntimeError("No days optimised successfully.")

    df = pd.concat(frames)
    df["revenue_cumulative"] = df["revenue_hourly"].cumsum()
    return df


def compute_revenue_stats(dispatch_df: pd.DataFrame, battery: BatteryParams) -> dict:
    """Summarise dispatch results into KPIs."""
    rev = dispatch_df["revenue_hourly"]
    n_days = (dispatch_df.index[-1] - dispatch_df.index[0]).days + 1

    # Equivalent full cycles
    total_discharge = dispatch_df["discharge_mw"].sum()  # MWh
    cycles = total_discharge / battery.capacity_mwh

    return {
        "total_revenue_usd": rev.sum(),
        "avg_daily_revenue_usd": rev.sum() / n_days,
        "revenue_per_mwh_capacity": rev.sum() / battery.capacity_mwh,
        "total_cycles": cycles,
        "avg_daily_cycles": cycles / n_days,
        "n_days": n_days,
        "capacity_factor_pct": dispatch_df["discharge_mw"].mean() / battery.power_mw * 100,
    }
