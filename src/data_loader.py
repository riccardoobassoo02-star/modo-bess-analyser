"""
ERCOT Day-Ahead Market price loader.
Primary: gridstatus library (pip install gridstatus)
Fallback: realistic synthetic ERCOT-like prices
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


ERCOT_HUBS = ["HB_NORTH", "HB_SOUTH", "HB_WEST", "HB_HOUSTON"]

def load_ercot_real_data(filepath: str, hub: str = "HB_NORTH") -> pd.DataFrame:
    """Load real ERCOT DAM SPP data from official yearly Excel file."""
    xl = pd.ExcelFile(filepath)
    
    all_dfs = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        filtered = df[df["Settlement Point"] == hub].copy()
        all_dfs.append(filtered)
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    # Gestisci 24:00 → giorno dopo 00:00
    df["Hour Ending"] = df["Hour Ending"].str.strip()
    mask_24 = df["Hour Ending"] == "24:00"
    df.loc[mask_24, "Hour Ending"] = "00:00"
    
    df["timestamp"] = pd.to_datetime(
        df["Delivery Date"].astype(str) + " " + df["Hour Ending"],
        format="%m/%d/%Y %H:%M"
    )
    df.loc[mask_24, "timestamp"] = df.loc[mask_24, "timestamp"] + pd.Timedelta(days=1)
    df["timestamp"] = df["timestamp"] - pd.Timedelta(hours=1)
    
    df = df.set_index("timestamp").sort_index()
    df = df[["Settlement Point Price"]].rename(
        columns={"Settlement Point Price": "price"}
    )
    
    return df 

def load_ercot_dam_prices(
    start_date: str, end_date: str, hub: str = "HB_NORTH"
) -> pd.DataFrame:
    """
    Load ERCOT Day-Ahead Market hourly LMP prices for a given hub.

    Tries gridstatus first; falls back to synthetic data if unavailable.

    Returns:
        DataFrame with DatetimeIndex and column 'price' ($/MWh)
    """
    try:
        import gridstatus

        iso = gridstatus.Ercot()
        df = iso.get_lmp(
            start=start_date,
            end=end_date,
            market="DAY_AHEAD_HOURLY",
            location_type="HUB",
        )
        df = df[df["Location"] == hub][["Time", "LMP"]].copy()
        df = df.rename(columns={"Time": "timestamp", "LMP": "price"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(
            "US/Central"
        )
        df = df.set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="first")]
        print(f"Loaded {len(df)} hours from ERCOT via gridstatus ({hub})")
        return df

    except Exception as e:
        print(f"Gridstatus unavailable ({type(e).__name__}). Let's try using synthetic data.")
        return _generate_synthetic_prices(start_date, end_date, hub)


def _generate_synthetic_prices(
    start_date: str, end_date: str, hub: str = "HB_NORTH"
) -> pd.DataFrame:
    """
    Generate realistic synthetic ERCOT DAM prices.
    Captures: diurnal shape, weekend discount, seasonal variation,
    occasional price spikes (scarcity events), negative prices.
    """
    rng = np.random.default_rng(seed=42 + hash(hub) % 1000)

    idx = pd.date_range(start=start_date, end=end_date, freq="h", tz="US/Central")
    n = len(idx)

    # Base diurnal profile (average weekday ERCOT shape)
    hourly_shape = np.array(
        [
            -8, -10, -11, -12, -10, -5,  # 0–5  (off-peak, negative possible)
             5,  12,  18,  20,  18,  16,  # 6–11 (morning ramp)
            14,  12,  10,  10,  12,  18,  # 12–17 (midday solar suppression)
            28,  35,  40,  38,  30,  18,  # 18–23 (evening peak)
        ],
        dtype=float,
    )

    # Seasonal base multiplier (Texas: summer >> winter)
    months = idx.month.values
    seasonal = np.where(
        months <= 2, 0.85,
        np.where(months <= 4, 0.90,
        np.where(months <= 6, 1.10,
        np.where(months <= 8, 1.40,  # summer heat
        np.where(months <= 10, 1.00, 0.80))))
    )

    # Weekend discount
    is_weekend = (idx.dayofweek >= 5).astype(float)
    weekend_adj = 1 - 0.15 * is_weekend

    # Base price = 35 $/MWh base + diurnal + seasonal
    base = 35.0 + hourly_shape[idx.hour.values]
    base = base * seasonal * weekend_adj

    # Add correlated noise (AR(1)-like)
    noise = np.zeros(n)
    eps = rng.normal(0, 6, n)
    for t in range(1, n):
        noise[t] = 0.6 * noise[t - 1] + eps[t]

    prices = base + noise

    # Spike events (~3% of hours in summer, 1% otherwise)
    spike_prob = np.where(months >= 6, 0.03, 0.01)[: n] 
    spike_mask = rng.random(n) < spike_prob
    spike_magnitude = rng.exponential(200, n)
    prices += spike_mask * spike_magnitude

    # Negative prices (~2% of off-peak hours on weekends)
    neg_mask = (
        (idx.hour.values < 7) & (is_weekend == 1) & (rng.random(n) < 0.25)
    )
    prices = np.where(neg_mask, -rng.uniform(5, 40, n), prices)

    df = pd.DataFrame({"price": prices}, index=idx)
    print(
        f"Generated {len(df)} hours of synthetic ERCOT prices ({hub}) "
        f"[mean={prices.mean():.1f}, max={prices.max():.0f}, min={prices.min():.0f} $/MWh]"
    )
    return df


def summarize_prices(df: pd.DataFrame) -> dict:
    """Return key descriptive statistics for a price series."""
    p = df["price"]
    return {
        "mean": p.mean(),
        "median": p.median(),
        "std": p.std(),
        "p5": p.quantile(0.05),
        "p95": p.quantile(0.95),
        "max": p.max(),
        "min": p.min(),
        "pct_negative": (p < 0).mean() * 100,
        "pct_above_100": (p > 100).mean() * 100,
        "n_hours": len(p),
    } 
def load_ercot_real_data(filepath: str, hub: str = "HB_NORTH") -> pd.DataFrame:
    """Load real ERCOT DAM SPP data from official yearly Excel file."""
    xl = pd.ExcelFile(filepath)
    
    all_dfs = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        filtered = df[df["Settlement Point"] == hub].copy()
        all_dfs.append(filtered)
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    # Gestisci 24:00 → converti manualmente senza pd.to_datetime diretto
    df["Hour Ending"] = df["Hour Ending"].astype(str).str.strip()
    
    def parse_ercot_timestamp(row):
        date_str = str(row["Delivery Date"]).strip()
        hour_str = row["Hour Ending"]
        if hour_str == "24:00":
            # mezzanotte del giorno dopo
            dt = pd.to_datetime(date_str, format="%m/%d/%Y") + pd.Timedelta(days=1)
        else:
            dt = pd.to_datetime(date_str + " " + hour_str, format="%m/%d/%Y %H:%M")
        return dt - pd.Timedelta(hours=1)  # Hour Ending → Hour Beginning
    
    df["timestamp"] = df.apply(parse_ercot_timestamp, axis=1)
    df = df.set_index("timestamp").sort_index()
    df = df[["Settlement Point Price"]].rename(
        columns={"Settlement Point Price": "price"}
    )
    
    return df
