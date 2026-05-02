"""
M6 — Security Score: pure backend logic (no Streamlit).

Implements three analytical functions used to evaluate Bitcoin network security:
  1. estimate_attack_cost_per_hour  — USD cost of a 51% attack per hour
  2. nakamoto_attack_probability    — double-spend success probability (Nakamoto 2008 §11)
  3. confirmation_safety_table      — safety percentages per confirmation depth
"""

import math


# ---------------------------------------------------------------------------
# Hardware / energy constants (Antminer S19 XP, as of 2024)
# ---------------------------------------------------------------------------

_ASIC_HASHRATE_THS  = 140        # TH/s (terahashes per second) per unit
_ASIC_POWER_W       = 3010       # Watts consumed per unit at rated hashrate
_ELECTRICITY_COST   = 0.05       # USD per kWh (global average for large miners)
_ATTACKER_FRACTION  = 0.51       # fraction of total hashrate needed for a 51% attack


def estimate_attack_cost_per_hour(hashrate_hs: float, btc_price_usd: float) -> float:
    """
    Estimate the USD cost per hour for a 51% attack on the Bitcoin network.

    Methodology:
      - An attacker must control at least 51% of the total network hashrate.
      - Assume they use Antminer S19 XP units: 140 TH/s at 3 010 W each.
      - Electricity cost is assumed to be $0.05 / kWh.

    Parameters
    ----------
    hashrate_hs   : total network hashrate in H/s (hashes per second)
    btc_price_usd : current BTC price in USD (reserved for future hardware-cost
                    extensions; not used in the electricity-only model)

    Returns
    -------
    float : estimated hourly electricity cost in USD to sustain the attack
    """
    # Target hashrate the attacker needs (51% of network)
    attacker_hashrate_hs = hashrate_hs * _ATTACKER_FRACTION

    # Convert to TH/s for comparison with the ASIC spec
    attacker_hashrate_ths = attacker_hashrate_hs / 1e12

    # Number of ASIC units required (ceiling so the attacker always has enough)
    n_machines = math.ceil(attacker_hashrate_ths / _ASIC_HASHRATE_THS)

    # Total power draw in kilowatts
    total_power_kw = (n_machines * _ASIC_POWER_W) / 1000  # W → kW

    # Hourly electricity cost: power_kW × 1 h × price_per_kWh
    cost_per_hour = total_power_kw * _ELECTRICITY_COST  # kW × h × $/kWh = USD

    return cost_per_hour


def nakamoto_attack_probability(q: float, z: int) -> float:
    """
    Compute the probability that an attacker with hash-rate fraction *q* can
    catch up from *z* blocks behind (Nakamoto 2008, section 11).

    Formula
    -------
    Let p = 1 - q  (honest fraction).
    If q >= 0.5, the attacker will always catch up eventually → return 1.0.
    Otherwise:
        P = 1 - sum_{k=0}^{z} [ (z! / k!) × (λ^k / k!) × e^{-λ} ×
            (1 - (q/p)^{z-k}) ]
    which simplifies to the closed-form series:
        P = sum_{k=0}^{z}  Poisson(k; λ) × (q/p)^{z-k}
    where λ = z × (q/p).

    Parameters
    ----------
    q : attacker's fraction of total hash rate (0 < q < 1)
    z : number of confirmations (blocks ahead the honest chain is)

    Returns
    -------
    float : probability of a successful double-spend attack (0.0 – 1.0)
    """
    if q >= 0.5:
        # Majority attacker always wins in expectation
        return 1.0

    p = 1.0 - q
    # λ is the expected number of blocks the attacker can generate
    # while the honest chain produces z blocks
    lam = z * (q / p)  # Poisson rate parameter

    # Sum Poisson-weighted terms: each term is the probability the attacker
    # emits exactly k blocks and then successfully extends from there
    total = 0.0
    for k in range(z + 1):
        # Poisson PMF: e^{-λ} × λ^k / k!
        poisson_pmf = math.exp(-lam) * (lam ** k) / math.factorial(k)
        # Probability of catching up from (z - k) blocks behind
        catchup = (q / p) ** (z - k)
        total += poisson_pmf * catchup

    # Clamp to [0, 1] to guard against floating-point overshoot
    return min(total, 1.0)


def confirmation_safety_table(q: float, max_confirmations: int = 10) -> list[dict]:
    """
    Build a table showing attack probability and safety percentage for each
    confirmation depth from 1 to *max_confirmations*.

    Parameters
    ----------
    q                 : attacker's hash-rate fraction (e.g. 0.1 for 10%)
    max_confirmations : highest confirmation depth to evaluate (default 10)

    Returns
    -------
    list[dict] with keys:
        confirmations      (int)   — number of confirmations
        attack_probability (float) — probability the attacker succeeds
        safety_percentage  (float) — 100 × (1 − attack_probability)
    """
    rows = []
    for z in range(1, max_confirmations + 1):
        prob = nakamoto_attack_probability(q, z)
        rows.append({
            "confirmations":      z,
            "attack_probability": prob,
            # safety is the complement: how confident you can be the payment is final
            "safety_percentage":  100.0 * (1.0 - prob),
        })
    return rows


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.blockchain_client import get_bitcoin_price_usd, get_current_hashrate

# theme styling constants
_BG       = "rgba(0,0,0,0)"
_FONT     = "#e2e8f0"
_PRIMARY  = "#6366f1"


def render() -> None:
    st.header("🛡️ M6 — Security Score")
    st.markdown(
        "Analyze the cost of a 51% attack and the probability of a successful "
        "double-spend based on Nakamoto's 2008 whitepaper."
    )

    # fetch data from API
    with st.spinner("Fetching network hashrate and BTC price..."):
        try:
            hashrate_hs = get_current_hashrate()
            btc_price = get_bitcoin_price_usd()
        except Exception as exc:
            st.error(f"⚠️ Failed to load network data: {exc}")
            return

    # calculate metrics
    hashrate_ehs = hashrate_hs / 1e18
    attack_cost = estimate_attack_cost_per_hour(hashrate_hs, btc_price)

    # display KPI metrics
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Network Hash Rate", f"{hashrate_ehs:.2f} EH/s")
    mc2.metric("Bitcoin Price", f"${btc_price:,.2f}")
    mc3.metric("51% Attack Cost (Hourly)", f"${attack_cost:,.0f}")

    st.divider()

    st.subheader("Attack probability analysis")
    
    # attacker hash rate fraction slider
    q = st.slider(
        "Attacker hash rate fraction (q)",
        min_value=0.01,
        max_value=0.49,
        value=0.25,
        step=0.01
    )

    max_conf = 15
    table_data = confirmation_safety_table(q, max_conf)

    # line chart for attack probability
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[r["confirmations"] for r in table_data],
        y=[r["attack_probability"] for r in table_data],
        mode="lines+markers",
        line=dict(color=_PRIMARY, width=2),
        marker=dict(size=8, color=_PRIMARY),
        name="Attack Probability"
    ))

    # 0.1% horizontal reference line
    fig.add_hline(
        y=0.001,
        line_dash="dash",
        line_color="rgba(239,68,68,0.8)",
        annotation_text="0.1% Threshold",
        annotation_font_color=_FONT
    )

    fig.update_layout(
        xaxis_title="Number of Confirmations",
        yaxis_title="Probability of Successful Attack",
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color=_FONT),
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Confirmation safety table")
    df = pd.DataFrame(table_data)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "confirmations": st.column_config.NumberColumn("Confirmations"),
            "attack_probability": st.column_config.NumberColumn("Attack Probability", format="%.6f"),
            "safety_percentage": st.column_config.NumberColumn("Safety (%)", format="%.4f")
        }
    )

    st.divider()

    st.subheader("Nakamoto 2008 formula")
    st.markdown(
        "The probability of an attacker catching up from `z` blocks behind "
        "is calculated using the formula described in Section 11 of the "
        "Bitcoin whitepaper. It models the block generation process as a "
        "Poisson random walk, where the expected number of blocks the attacker "
        "mines while the honest network mines `z` blocks is `λ = z * (q/p)`."
    )
