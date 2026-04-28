"""
M1 — Proof of Work Monitor
===========================
This module visualises three core aspects of Bitcoin's Proof-of-Work (PoW)
mechanism using live data from the Blockstream public API:

  Section 1 — Current Difficulty & Leading-Zero Visualisation
  Section 2 — Inter-block Time Histogram (last 50 blocks)
  Section 3 — Estimated Network Hash Rate
"""

import math
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.blockchain_client import (
    get_latest_block,
    get_recent_block_timestamps,
    get_hashrate,
)


# ---------------------------------------------------------------------------
# Helper: decode the "bits" compact target → number of leading zero bits
# ---------------------------------------------------------------------------

def bits_to_leading_zeros(bits: int) -> int:
    """
    Convert the compact 'bits' field from a Bitcoin block header into the
    approximate number of leading zero *bits* required in a valid block hash.

    The 'bits' field is a 32-bit compact representation of the 256-bit target T:

        bits = [exponent (1 byte)] [coefficient (3 bytes)]   (big-endian layout)

        T = coefficient × 256^(exponent − 3)

    The number of leading zero bits in T equals:
        leading_zeros ≈ 256 − floor(log2(T + 1))

    In practice:
        exponent = bits >> 24            (most-significant byte)
        coefficient = bits & 0x00FFFFFF  (lower 3 bytes)
        T = coefficient * (256 ** (exponent - 3))
        leading_zero_bits = 256 - T.bit_length()

    Note: The bits value in Blockstream's JSON is already decoded as an
    integer (it is NOT stored in little-endian at this point — the API
    returns it in host byte order).
    """
    exponent = (bits >> 24) & 0xFF       # top byte: size of the target in bytes
    coefficient = bits & 0x00FFFFFF      # lower 3 bytes: significant digits

    if coefficient == 0:
        return 256  # edge case: zero target (impossible in practice)

    # Reconstruct the full 256-bit target value
    byte_shift = exponent - 3            # how many bytes to left-shift the coefficient
    if byte_shift >= 0:
        target = coefficient << (byte_shift * 8)
    else:
        target = coefficient >> ((-byte_shift) * 8)

    if target <= 0:
        return 256

    # Number of leading zero bits = total bits − significant bits of target
    leading_zeros = 256 - target.bit_length()
    return max(0, leading_zeros)


# ---------------------------------------------------------------------------
# Section 1 — Difficulty & Leading Zeros
# ---------------------------------------------------------------------------

def _render_difficulty_section(block: dict) -> None:
    """Display current difficulty and a visual of SHA-256 leading zeros."""
    st.subheader("🔒 Section 1 — Current Difficulty & SHA-256 Target")

    difficulty = block.get("difficulty", 0)
    bits = block.get("bits", 0)
    block_hash = block.get("id", "N/A")
    height = block.get("height", "N/A")
    nonce = block.get("nonce", "N/A")
    tx_count = block.get("tx_count", "N/A")

    leading_zeros = bits_to_leading_zeros(bits)
    leading_zero_bytes = leading_zeros // 8
    leading_zero_bits_remainder = leading_zeros % 8

    # ── KPI cards ──────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Block Height", f"{height:,}" if isinstance(height, int) else height)
    col2.metric("Difficulty", f"{difficulty / 1e12:.3f} T")
    col3.metric("Leading Zero Bits", leading_zeros)
    col4.metric("Nonce", f"{nonce:,}" if isinstance(nonce, int) else nonce)

    st.caption(
        f"Latest block hash: `{block_hash}`  |  Transactions: {tx_count:,}"
        if isinstance(tx_count, int) else f"Latest block hash: `{block_hash}`"
    )

    # ── Explain bits encoding ───────────────────────────────────────────────
    with st.expander("ℹ️ How is 'bits' decoded into leading zeros?"):
        st.markdown(f"""
**`bits` field value:** `{hex(bits)}` (compact target, uint32)

The `bits` field encodes the 256-bit PoW *target threshold* T in a compact
form analogous to floating-point notation:

```
bits = [exponent (1 byte)] [coefficient (3 bytes)]
T = coefficient × 256^(exponent − 3)
```

A valid block hash **must be numerically less than T**.  
Because T is a very small number relative to 2²⁵⁶, it starts with many
leading zero bits.

**Current target requires ≈ {leading_zeros} leading zero bits**  
({leading_zero_bytes} full zero bytes + {leading_zero_bits_remainder} additional zero bits)

This means on average a miner must try **2^{leading_zeros} ≈ {2**leading_zeros:.2e}**
different nonces before finding a valid hash — that is why mining is computationally
expensive.
""")

    # ── 256-bit visual bar ──────────────────────────────────────────────────
    st.markdown("#### SHA-256 Hash Space: leading-zero constraint visualised")

    # We represent the 256-bit space as a horizontal stacked bar
    zero_pct = (leading_zeros / 256) * 100
    valid_pct = 100 - zero_pct

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Required leading zeros",
        x=[zero_pct],
        y=["256-bit hash space"],
        orientation="h",
        marker_color="#ef4444",
        text=[f"{leading_zeros} bits (≈{zero_pct:.1f}%)"],
        textposition="inside",
        insidetextanchor="middle",
    ))
    fig.add_trace(go.Bar(
        name="Remaining bits",
        x=[valid_pct],
        y=["256-bit hash space"],
        orientation="h",
        marker_color="#22c55e",
        text=[f"{256 - leading_zeros} bits (≈{valid_pct:.1f}%)"],
        textposition="inside",
        insidetextanchor="middle",
    ))

    fig.update_layout(
        barmode="stack",
        title=dict(
            text=f"SHA-256 PoW Constraint — {leading_zeros} leading zero bits required",
            font=dict(size=15),
        ),
        xaxis=dict(
            title="Percentage of 256-bit hash space",
            ticksuffix="%",
            range=[0, 100],
        ),
        yaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=160,
        margin=dict(l=10, r=10, t=60, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )

    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 2 — Inter-block Time Histogram
# ---------------------------------------------------------------------------

def _render_interblock_histogram(timestamps: list[int]) -> None:
    """Plot inter-block time histogram and overlay theoretical Exponential PDF."""
    st.subheader("⏱️ Section 2 — Inter-block Time Distribution (last 50 blocks)")

    if len(timestamps) < 2:
        st.warning("Not enough block data to compute inter-block times.")
        return

    # timestamps arrive in descending order (newest first)
    sorted_ts = sorted(timestamps, reverse=True)
    inter_block_times = [
        sorted_ts[i] - sorted_ts[i + 1]
        for i in range(len(sorted_ts) - 1)
    ]

    df = pd.DataFrame({"inter_block_seconds": inter_block_times})
    mean_time = df["inter_block_seconds"].mean()
    median_time = df["inter_block_seconds"].median()

    col1, col2, col3 = st.columns(3)
    col1.metric("Blocks analysed", len(inter_block_times))
    col2.metric("Mean inter-block time", f"{mean_time:.0f} s  ({mean_time/60:.1f} min)")
    col3.metric("Median inter-block time", f"{median_time:.0f} s  ({median_time/60:.1f} min)")

    # ── Histogram ───────────────────────────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=df["inter_block_seconds"],
        nbinsx=20,
        name="Observed inter-block times",
        marker_color="#6366f1",
        opacity=0.85,
    ))

    # Overlay theoretical exponential PDF (scaled to counts)
    import numpy as np
    x_range = np.linspace(0, max(inter_block_times) * 1.1, 300)
    lam = 1.0 / mean_time  # rate parameter
    bin_width = (max(inter_block_times)) / 20
    n_samples = len(inter_block_times)
    # Scale PDF to match histogram counts
    pdf_scaled = lam * np.exp(-lam * x_range) * n_samples * bin_width

    fig.add_trace(go.Scatter(
        x=x_range,
        y=pdf_scaled,
        mode="lines",
        name=f"Exp(λ=1/{mean_time:.0f}s) — theoretical",
        line=dict(color="#f59e0b", width=2.5, dash="dash"),
    ))

    # Mark the mean
    fig.add_vline(
        x=mean_time,
        line_color="#22c55e",
        line_dash="dot",
        annotation_text=f"Mean = {mean_time:.0f}s",
        annotation_position="top right",
        annotation_font_color="#22c55e",
    )

    fig.update_layout(
        title=dict(
            text=(
                "Inter-block Times — Last 50 Bitcoin Blocks<br>"
                "<sup>Expected distribution: Exponential (memoryless Poisson process)</sup>"
            ),
            font=dict(size=15),
        ),
        xaxis=dict(title="Inter-block time (seconds)"),
        yaxis=dict(title="Number of blocks"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.05,
        height=420,
        margin=dict(l=10, r=10, t=80, b=50),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.07)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.07)")

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📖 Why exponential? — theoretical explanation"):
        st.markdown("""
**Mining as a Poisson process**

Each miner repeatedly computes SHA-256(SHA-256(block_header)) with a
different nonce and checks if the result is below the target T.

- Each hash attempt is **independent** of all previous ones.
- The probability of success per attempt is constant: p ≈ 1 / 2^(leading_zeros).
- The entire network performs ≈ *hash_rate* attempts per second.

This is a **Bernoulli process** in discrete time, which converges to a
**Poisson process** in the continuous limit.

The waiting time until the next success in a Poisson process is
**Exponentially distributed** with rate λ = network_hash_rate × p.

The Bitcoin protocol adjusts difficulty every 2,016 blocks so that
λ⁻¹ ≈ 600 seconds (10 minutes).

**Key insight:** the Exponential distribution is *memoryless*:
> "The expected time until the next block is always ~10 min,
> regardless of how long we have already been waiting."

This is in stark contrast to a deterministic or uniform distribution,
and it explains why sometimes two blocks arrive within a minute while
other times miners wait 30+ minutes.
""")


# ---------------------------------------------------------------------------
# Section 3 — Estimated Network Hash Rate
# ---------------------------------------------------------------------------

def _render_hashrate_section(hashrate_hs: float, difficulty: float) -> None:
    """Display the estimated current network hash rate."""
    st.subheader("⚡ Section 3 — Estimated Network Hash Rate")

    # Convert to human-readable units
    hashrate_ehs = hashrate_hs / 1e18   # ExaHash/s
    hashrate_phs = hashrate_hs / 1e15   # PetaHash/s
    hashrate_zhs = hashrate_hs / 1e21   # ZettaHash/s (for future scale)

    col1, col2, col3 = st.columns(3)
    col1.metric("Hash Rate (EH/s)", f"{hashrate_ehs:.2f} EH/s")
    col2.metric("Hash Rate (PH/s)", f"{hashrate_phs:,.0f} PH/s")
    col3.metric("Difficulty", f"{difficulty / 1e12:.3f} T")

    with st.expander("🔢 How is hash rate estimated?"):
        st.markdown(f"""
**Formula:**

```
hash_rate ≈ difficulty × 2³² / 600
```

**Derivation:**

1. A valid hash must be numerically less than the target T.
2. The probability that a single SHA-256 output is below T is:
   `p = T / 2²⁵⁶`
3. The difficulty is defined as:
   `difficulty = difficulty_1_target / T`
   where `difficulty_1_target = 0x00000000FFFF0000...0000` (genesis target).
4. On average, a miner needs `1/p ≈ difficulty × 2³²` hashes to find one block.
5. With a target block time of 600 seconds:
   `hash_rate = (difficulty × 2³²) / 600`

**Current values:**
- Difficulty: `{difficulty:.6e}`
- Estimated hash rate: `{hashrate_ehs:.3f} EH/s`
  = `{hashrate_hs:.3e}` H/s

*Note: This is a network-wide estimate. Individual miner hash rates are unknown
to the protocol — only the aggregate effect is observable through block timing.*
""")

    # ── Visual gauge ────────────────────────────────────────────────────────
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=hashrate_ehs,
        number=dict(suffix=" EH/s", font=dict(size=36, color="#e2e8f0")),
        delta=dict(reference=600, relative=False),  # placeholder reference
        title=dict(text="Network Hash Rate", font=dict(size=16, color="#e2e8f0")),
        gauge=dict(
            axis=dict(
                range=[0, 1200],
                tickwidth=1,
                tickcolor="#e2e8f0",
                tickfont=dict(color="#e2e8f0"),
            ),
            bar=dict(color="#6366f1"),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=1,
            bordercolor="#334155",
            steps=[
                dict(range=[0, 300], color="rgba(239,68,68,0.2)"),
                dict(range=[300, 600], color="rgba(245,158,11,0.2)"),
                dict(range=[600, 900], color="rgba(34,197,94,0.2)"),
                dict(range=[900, 1200], color="rgba(99,102,241,0.2)"),
            ],
            threshold=dict(
                line=dict(color="#f59e0b", width=3),
                thickness=0.75,
                value=hashrate_ehs,
            ),
        ),
    ))

    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )

    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the complete M1 — Proof of Work Monitor panel."""
    st.header("⛏️  M1 — Proof of Work Monitor")
    st.markdown(
        "Live Bitcoin mining data fetched from the "
        "[Blockstream API](https://blockstream.info/api/) · "
        "Auto-refreshes every 60 seconds."
    )

    # ── Data fetching (with graceful error handling) ──────────────────────
    with st.spinner("Fetching live Bitcoin data…"):
        fetch_error = None
        block = None
        timestamps = None
        hashrate_hs = None

        try:
            block = get_latest_block()
        except Exception as exc:
            fetch_error = f"Could not fetch latest block: {exc}"

        try:
            timestamps = get_recent_block_timestamps(50)
        except Exception as exc:
            if fetch_error:
                fetch_error += f"\n\nCould not fetch block timestamps: {exc}"
            else:
                fetch_error = f"Could not fetch block timestamps: {exc}"

        try:
            hashrate_hs = get_hashrate()
        except Exception as exc:
            if fetch_error:
                fetch_error += f"\n\nCould not fetch hash rate: {exc}"
            else:
                fetch_error = f"Could not fetch hash rate: {exc}"

    if fetch_error:
        st.error(f"⚠️ API Error — partial data may be shown:\n\n{fetch_error}")

    st.divider()

    # ── Section 1 ─────────────────────────────────────────────────────────
    if block is not None:
        _render_difficulty_section(block)
    else:
        st.warning("Section 1 unavailable — block data could not be retrieved.")

    st.divider()

    # ── Section 2 ─────────────────────────────────────────────────────────
    if timestamps is not None:
        _render_interblock_histogram(timestamps)
    else:
        st.warning("Section 2 unavailable — timestamp data could not be retrieved.")

    st.divider()

    # ── Section 3 ─────────────────────────────────────────────────────────
    difficulty = float(block["difficulty"]) if block else 0.0
    if hashrate_hs is not None:
        _render_hashrate_section(hashrate_hs, difficulty)
    elif block is not None:
        # Fallback: compute hash rate from block difficulty directly
        difficulty = float(block.get("difficulty", 0))
        hashrate_hs = difficulty * (2 ** 32) / 600  # H = D × 2³² / 600 s
        _render_hashrate_section(hashrate_hs, difficulty)
    else:
        st.warning("Section 3 unavailable — hash rate could not be estimated.")
