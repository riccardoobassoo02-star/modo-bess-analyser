# ⚡ BESS Arbitrage Analyser · ERCOT

An interactive tool to evaluate battery energy storage (BESS) revenue from day-ahead energy arbitrage in the ERCOT market, including full project financial analysis.

Built as part of the **Modo Energy Take-Home Task**.

---

## Live Demo

🔗 [Launch the app on Streamlit Cloud](https://modo-bess-analyser-dmjdaj86xxkusbdceehprv.streamlit.app/)

---

## Why This Project

BESS arbitrage sits at the intersection of energy markets, optimization, and project finance — exactly the problems Modo works on, and the areas I want to go deeper into. I wanted to build something that answers a real commercial question: *"Is this battery worth building?"*

I scoped it to three layers:
1. **Market analysis** — understand the price structure that drives revenue
2. **Dispatch optimisation** — LP model to find the optimal charge/discharge strategy
3. **Financial analysis** — LCOS and payback to translate revenue into investment decisions

This mirrors how a real analyst would approach a BESS opportunity. 

## The Question

> *"How much revenue can a battery storage asset earn from day-ahead energy arbitrage in ERCOT, and what drives that revenue?"*

---

## Key Results — ERCOT 2023, HB_NORTH, 1 MW / 2 MWh

### Revenue
| Metric | Value |
|--------|-------|
| Total Revenue | **$81,356** |
| Avg Daily Revenue | **$222/day** |
| Revenue / MWh Capacity | **$40,678/MWh** |
| Total Cycles | **814** |
| Avg Price | **$49.2/MWh** |

> Rolling day-ahead dispatch · 85% round-trip efficiency · 2023-01-01 → 2023-12-31

### Project Financials
| Metric | Value |
|--------|-------|
| Total CAPEX | **$600,000** |
| Annual O&M | **$6,000/year** |
| Payback Period | **8.7 years** |
| LCOS | **$52.3/MWh** |

> CAPEX: $300/kWh · WACC: 8% · Project life: 15 years · Annual degradation: 2%

---

## What the Tool Does

The app answers four questions:

**1. 📊 What does the price structure look like?**
- Heatmap of median prices by hour and day of week
- Price duration curve
- Key statistics (mean, std, P5/P95, % negative, % above $100)

**2. ⚡ How does the battery dispatch?**
- Optimal charge/discharge schedule via Linear Programming
- State of charge trajectory
- Average dispatch profile by hour of day

**3. 💰 How much revenue does it generate?**
- Cumulative revenue over the year
- Monthly revenue breakdown
- Annualised revenue estimate

**4. 💼 Is the project financially viable?**
- LCOS vs market price spread
- Payback period
- Annual and cumulative cash flow chart

---

## Methodology

### Optimisation

The dispatch is formulated as a **Linear Program** solved with [HiGHS](https://highs.dev/) via `scipy.optimize.linprog`:

```
maximise  Σ price[t] × (discharge[t] - charge[t]) × Δt

subject to:
  e[t] = e[t-1] + η_c × charge[t] - (1/η_d) × discharge[t]   (SoC dynamics)
  0 ≤ charge[t], discharge[t] ≤ P_max                          (power limits)
  E_min ≤ e[t] ≤ E_max                                         (SoC bounds)
```

### Two dispatch modes

| Mode | Description | Use case |
|------|-------------|----------|
| **Rolling day-ahead** | Optimises 24h at a time, SoC carries over | Realistic simulation |
| **Perfect foresight** | Optimises full period at once | Theoretical upper bound |

The gap between the two represents the **value of perfect price forecasting**.

### LCOS

The Levelized Cost of Storage is computed as:

```
LCOS = (CAPEX + NPV of OPEX) / NPV of total discharged energy
```

It represents the minimum price spread required to break even over the project life — the key metric for investment decisions.

### Data

- **Real data**: ERCOT DAM Settlement Point Prices (NP4-180-ER) for 2023
- **Synthetic data**: Calibrated on ERCOT statistics — mean $35/MWh, seasonal summer peak ×1.4, 3% spike probability

---

## Battery Parameters

| Parameter | Default | Range |
|-----------|---------|-------|
| Power | 1 MW | 0.5 – 10 MW |
| Duration | 2 hours | 1 – 8 hours |
| Round-trip efficiency | 85% | 70 – 97% |
| Min SoC | 10% | 0 – 30% |
| Max SoC | 90% | 70 – 100% |

---

## Project Structure

```
modo-bess-analyser/
├── app.py                  # Streamlit dashboard
├── src/
│   ├── data_loader.py      # ERCOT data loading (real + synthetic)
│   ├── optimizer.py        # LP dispatch optimisation
│   ├── financial.py        # LCOS and payback analysis
│   └── viz.py              # Plotly visualisations
├── data/
│   └── rpt.00013060...xlsx # ERCOT 2023 DAM prices
└── requirements.txt
```

---

## Installation

```bash
git clone https://github.com/your-username/modo-bess-analyser
cd modo-bess-analyser
conda create -n modo python=3.11
conda activate modo
pip install -r requirements.txt
streamlit run app.py
```

---

## Limitations & Extensions

This tool models **energy-only arbitrage** — the conservative floor of BESS revenue. Real assets stack additional revenues:

- **Ancillary services** (ECRS, Reg-Up/Down, Non-Spin) — typically 30–60% additional revenue in ERCOT
- **Degradation costs** — modelled as 2% annual capacity loss
- **Financing structure** — simplified single WACC; real projects use debt/equity split

Natural extensions:
- Multi-service co-optimisation (energy + ancillary)
- Price forecasting to replace perfect foresight
- Hub comparison across HB_NORTH, HB_WEST, HB_SOUTH, HB_HOUSTON
- Sensitivity analysis on CAPEX and duration

---

## How I Used AI

I used Claude (Anthropic) throughout this project:
- **Code generation** — scaffolding the LP formulation, Streamlit layout, Plotly charts
- **Debugging** — fixing scipy/pandas issues, Plotly layout conflicts
- **Learning** — understanding ERCOT market structure, LP duality, LCOS methodology

The workflow was iterative: I'd define what I wanted, Claude would generate a first version, I'd test it, identify issues, and refine. The key skill was knowing *what* to ask for and *whether the output made sense* — not just accepting generated code blindly.

## Author

**Riccardo Basso**
MSc Sustainable Energy Systems — Technical University of Denmark (DTU)