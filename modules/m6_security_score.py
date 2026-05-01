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
