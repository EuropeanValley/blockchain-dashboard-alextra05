"""
M4 — AI Component: Inter-block Time Anomaly Detector
======================================================
Detects anomalous Bitcoin inter-block times using a statistical Exponential
distribution model. Thresholds: upper = mean + 3*std, lower = 30 s.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.blockchain_client import get_recent_block_timestamps

TARGET_BLOCK_TIME_S = 600   # Bitcoin's 10-minute target
MIN_BLOCK_TIME_S = 30       # Lower-bound threshold (< 30 s is suspicious)
N_STD_UPPER = 3             # Upper threshold: mean + N_STD * std


# ---------------------------------------------------------------------------
# Core anomaly detection
# ---------------------------------------------------------------------------

def _compute_inter_block_times(timestamps: list[int]) -> np.ndarray:
    """
    Compute inter-block times from a list of Unix timestamps.
    Timestamps arrive in **descending** order (newest first).
    """
    sorted_ts = sorted(timestamps, reverse=True)   # newest first
    times = np.array([
        sorted_ts[i] - sorted_ts[i + 1]
        for i in range(len(sorted_ts) - 1)
    ], dtype=float)
    return times


def _detect_anomalies(
    times: np.ndarray,
    mean: float,
    std: float,
) -> np.ndarray:
    """
    Return a boolean mask where True indicates an anomalous inter-block time.

    Anomaly conditions (either triggers a flag):
      1. time > mean + N_STD_UPPER * std   → unusually long gap
      2. time < MIN_BLOCK_TIME_S           → suspiciously short gap
    """
    upper_threshold = mean + N_STD_UPPER * std
    anomaly_mask = (times > upper_threshold) | (times < MIN_BLOCK_TIME_S)
    return anomaly_mask


def _anomaly_reason(t: float, mean: float, std: float) -> str:
    """Return a human-readable reason for why a block is flagged."""
    upper = mean + N_STD_UPPER * std
    reasons = []
    if t > upper:
        reasons.append(f"Gap {t:.0f}s > upper threshold {upper:.0f}s (mean + 3σ)")
    if t < MIN_BLOCK_TIME_S:
        reasons.append(f"Gap {t:.0f}s < minimum threshold {MIN_BLOCK_TIME_S}s")
    return " | ".join(reasons) if reasons else "Normal"


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the complete M4 — AI Anomaly Detector panel."""
    st.header("🤖  M4 — AI Component: Inter-block Time Anomaly Detector")
    st.markdown(
        "Uses a **statistical Exponential distribution model** to detect "
        "anomalous inter-block times in recent Bitcoin blocks.  \n"
        "Data source: [Blockstream API](https://blockstream.info/api/)"
    )

    # ── Controls ───────────────────────────────────────────────────────────
    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl1:
        n_blocks = st.slider(
            "Number of recent blocks to analyze",
            min_value=50,
            max_value=200,
            value=200,
            step=10,
            key="m4_n_blocks",
        )
    with col_ctrl2:
        run_btn = st.button("🚀 Run Detector", key="m4_run", use_container_width=True)

    if not run_btn:
        st.info(
            "Select the number of blocks to analyze and click **Run Detector**. "
            "The model will flag blocks whose inter-block gap deviates significantly "
            "from Bitcoin's expected ~600 s Exponential distribution."
        )
        return

    # ── Fetch timestamps ───────────────────────────────────────────────────
    with st.spinner(f"Fetching {n_blocks} recent block timestamps…"):
        try:
            timestamps = get_recent_block_timestamps(n_blocks)
        except Exception as exc:
            st.error(f"⚠️ Failed to fetch block timestamps: {exc}")
            return

    if len(timestamps) < 3:
        st.warning("Not enough timestamps returned to perform analysis.")
        return

    # ── Compute inter-block times ──────────────────────────────────────────
    times = _compute_inter_block_times(timestamps)
    n_times = len(times)

    mean_time = float(np.mean(times))
    std_time = float(np.std(times))
    upper_threshold = mean_time + N_STD_UPPER * std_time

    anomaly_mask = _detect_anomalies(times, mean_time, std_time)
    n_anomalies = int(anomaly_mask.sum())
    pct_anomalies = (n_anomalies / n_times) * 100

    block_indices = np.arange(n_times)

    # ── Evaluation metrics ─────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Model Evaluation Metrics")

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total Blocks Analyzed", n_times)
    mc2.metric("Anomalies Detected", n_anomalies)
    mc3.metric("Anomaly Rate", f"{pct_anomalies:.1f}%")
    mc4.metric("Mean Inter-block Time", f"{mean_time:.0f} s  ({mean_time/60:.1f} min)")

    st.divider()

    # ── Scatter plot ───────────────────────────────────────────────────────
    st.subheader("🔍 Inter-block Times — Scatter Plot")
    st.caption(
        f"Upper anomaly threshold: **mean + 3σ = {upper_threshold:.0f} s** "
        f"({upper_threshold/60:.1f} min) · Lower threshold: **{MIN_BLOCK_TIME_S} s**"
    )

    normal_idx = block_indices[~anomaly_mask]
    anomaly_idx = block_indices[anomaly_mask]

    fig = go.Figure()

    # Normal blocks
    fig.add_trace(go.Scatter(
        x=normal_idx,
        y=times[~anomaly_mask],
        mode="markers",
        name="Normal block",
        marker=dict(
            color="#6366f1",
            size=6,
            opacity=0.75,
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        hovertemplate=(
            "Block index: %{x}<br>"
            "Inter-block time: %{y:.0f} s (%{customdata:.1f} min)<extra></extra>"
        ),
        customdata=times[~anomaly_mask] / 60,
    ))

    # Anomalous blocks
    if n_anomalies > 0:
        fig.add_trace(go.Scatter(
            x=anomaly_idx,
            y=times[anomaly_mask],
            mode="markers",
            name="Anomalous block 🔴",
            marker=dict(
                color="#ef4444",
                size=10,
                symbol="circle",
                opacity=0.95,
                line=dict(color="#ffffff", width=1.5),
            ),
            hovertemplate=(
                "<b>⚠️ ANOMALY</b><br>"
                "Block index: %{x}<br>"
                "Inter-block time: %{y:.0f} s (%{customdata:.1f} min)<extra></extra>"
            ),
            customdata=times[anomaly_mask] / 60,
        ))

    # Upper threshold line
    fig.add_hline(
        y=upper_threshold,
        line_color="#f59e0b",
        line_dash="dash",
        line_width=1.8,
        annotation_text=f"Upper threshold: {upper_threshold:.0f} s (mean + 3σ)",
        annotation_font_color="#f59e0b",
        annotation_position="top right",
    )

    # Target line (600 s)
    fig.add_hline(
        y=TARGET_BLOCK_TIME_S,
        line_color="#22c55e",
        line_dash="dot",
        line_width=1.5,
        annotation_text="Target: 600 s (10 min)",
        annotation_font_color="#22c55e",
        annotation_position="bottom right",
    )

    # Lower threshold line
    fig.add_hline(
        y=MIN_BLOCK_TIME_S,
        line_color="#ef4444",
        line_dash="dot",
        line_width=1.5,
        annotation_text=f"Lower threshold: {MIN_BLOCK_TIME_S} s",
        annotation_font_color="#ef4444",
        annotation_position="top left",
    )

    fig.update_layout(
        title=dict(
            text=(
                f"Inter-block Times — Last {n_times} Blocks<br>"
                "<sup>Red = anomalous · Blue = normal · "
                "Thresholds derived from Exponential distribution model</sup>"
            ),
            font=dict(size=15, color="#e2e8f0"),
        ),
        xaxis=dict(
            title="Block Index (0 = oldest, right = newest)",
            gridcolor="rgba(255,255,255,0.07)",
            tickfont=dict(color="#e2e8f0"),
            title_font=dict(color="#e2e8f0"),
        ),
        yaxis=dict(
            title="Inter-block Time (seconds)",
            gridcolor="rgba(255,255,255,0.07)",
            tickfont=dict(color="#e2e8f0"),
            title_font=dict(color="#e2e8f0"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#e2e8f0"),
        ),
        height=480,
        margin=dict(l=10, r=10, t=100, b=60),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
        hovermode="closest",
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Anomaly table ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("⚠️ Detected Anomalies — Summary Table")

    if n_anomalies == 0:
        st.success(
            "✅ No anomalies detected in this sample. "
            "All inter-block times fall within expected bounds of the Exponential model."
        )
    else:
        anomaly_rows = []
        for idx in anomaly_idx:
            t = times[idx]
            reason = _anomaly_reason(t, mean_time, std_time)
            tag = "⬆️ Too slow" if t > upper_threshold else "⬇️ Too fast"
            anomaly_rows.append({
                "Block Index": int(idx),
                "Inter-block Time (s)": round(float(t), 1),
                "Time (min)": round(float(t) / 60, 2),
                "Type": tag,
                "Reason": reason,
            })

        anomaly_df = pd.DataFrame(anomaly_rows)
        st.dataframe(
            anomaly_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Block Index": st.column_config.NumberColumn("Block Index", width="small"),
                "Inter-block Time (s)": st.column_config.NumberColumn("Time (s)", width="small"),
                "Time (min)": st.column_config.NumberColumn("Time (min)", width="small"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Reason": st.column_config.TextColumn("Reason", width="large"),
            },
        )

    # ── Distribution plot ──────────────────────────────────────────────────
    st.divider()
    st.subheader("📐 Inter-block Time Distribution vs. Exponential Model")

    x_range = np.linspace(0, max(times) * 1.1, 400)
    lam_empirical = 1.0 / mean_time
    bin_width = max(times) / 25
    pdf_scaled = lam_empirical * np.exp(-lam_empirical * x_range) * n_times * bin_width

    fig2 = go.Figure()

    fig2.add_trace(go.Histogram(
        x=times,
        nbinsx=25,
        name="Observed inter-block times",
        marker_color="#6366f1",
        opacity=0.75,
    ))

    fig2.add_trace(go.Scatter(
        x=x_range,
        y=pdf_scaled,
        mode="lines",
        name=f"Exp(λ=1/{mean_time:.0f}s) — fitted model",
        line=dict(color="#f59e0b", width=2.5, dash="dash"),
    ))

    fig2.add_vline(
        x=upper_threshold,
        line_color="#ef4444",
        line_dash="dot",
        line_width=1.8,
        annotation_text=f"Upper threshold: {upper_threshold:.0f}s",
        annotation_font_color="#ef4444",
        annotation_position="top right",
    )

    fig2.add_vline(
        x=mean_time,
        line_color="#22c55e",
        line_dash="dot",
        line_width=1.5,
        annotation_text=f"Mean: {mean_time:.0f}s",
        annotation_font_color="#22c55e",
        annotation_position="top left",
    )

    fig2.update_layout(
        title=dict(
            text=(
                "Inter-block Time Histogram with Fitted Exponential Model<br>"
                "<sup>The red dashed line marks the anomaly threshold (mean + 3σ)</sup>"
            ),
            font=dict(size=15, color="#e2e8f0"),
        ),
        xaxis=dict(
            title="Inter-block Time (seconds)",
            gridcolor="rgba(255,255,255,0.07)",
            tickfont=dict(color="#e2e8f0"),
            title_font=dict(color="#e2e8f0"),
        ),
        yaxis=dict(
            title="Number of blocks",
            gridcolor="rgba(255,255,255,0.07)",
            tickfont=dict(color="#e2e8f0"),
            title_font=dict(color="#e2e8f0"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#e2e8f0"),
        ),
        bargap=0.05,
        height=400,
        margin=dict(l=10, r=10, t=90, b=60),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )

    st.plotly_chart(fig2, use_container_width=True)


