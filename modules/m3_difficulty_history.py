"""
M3 — Difficulty History
========================
Plots the evolution of Bitcoin's mining difficulty over time, marks each
difficulty adjustment epoch (every 2,016 blocks), and shows the ratio of
actual vs. target block time for each adjustment period.

Background:
  - Bitcoin's difficulty re-targets every 2,016 blocks (~2 weeks).
  - The adjustment formula is:
        new_difficulty = old_difficulty × (actual_time / target_time)
    where target_time = 2016 × 600 seconds = 1,209,600 seconds.
  - If miners found blocks faster than 10 min/block the difficulty rises;
    if slower, it falls.  The ratio actual/target is shown per epoch.
"""

import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.blockchain_client import get_difficulty_history

# Bitcoin's difficulty adjustment interval (blocks)
EPOCH_BLOCKS = 2016
TARGET_BLOCK_TIME_S = 600  # 10 minutes per block
TARGET_EPOCH_TIME_S = EPOCH_BLOCKS * TARGET_BLOCK_TIME_S  # 1,209,600 s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_dataframe(history: list[dict]) -> pd.DataFrame:
    """Convert raw history list to a tidy DataFrame."""
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["x"], unit="s", utc=True)
    df["difficulty"] = df["y"].astype(float)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _detect_adjustment_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify rows where difficulty changes — these correspond to epoch
    boundaries.  Returns a subset of df with an added 'ratio' column
    representing actual_epoch_time / target_epoch_time.
    """
    # A difficulty change signals a new epoch
    df = df.copy()
    df["diff_change"] = df["difficulty"].diff().abs()
    adjustment_idx = df[df["diff_change"] > 0].index.tolist()

    rows = []
    for i, idx in enumerate(adjustment_idx):
        row = df.loc[idx].copy()
        # Estimate actual epoch time from timestamps of consecutive adjustments
        if i > 0:
            prev_idx = adjustment_idx[i - 1]
            prev_ts = df.loc[prev_idx, "x"]
            curr_ts = df.loc[idx, "x"]
            actual_epoch_s = curr_ts - prev_ts
            row["actual_epoch_s"] = actual_epoch_s
            row["ratio"] = actual_epoch_s / TARGET_EPOCH_TIME_S
        else:
            row["actual_epoch_s"] = np.nan
            row["ratio"] = np.nan
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    adj_df = pd.DataFrame(rows).reset_index(drop=True)
    return adj_df


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the complete M3 — Difficulty History panel."""
    st.header("📈  M3 — Difficulty History")
    st.markdown(
        "Track how Bitcoin's mining difficulty has evolved over time, "
        "and examine each difficulty-adjustment event.  \n"
        "Data source: [Blockstream API](https://blockstream.info/api/)"
    )

    # ── Controls ──────────────────────────────────────────────────────────
    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl1:
        n_points = st.slider(
            "Number of recent blocks to sample",
            min_value=20,
            max_value=500,
            value=150,
            step=10,
            key="m3_n_points",
            help=(
                "Each data point represents one recent block. "
                "Higher values cover more history but take longer to fetch."
            ),
        )
    with col_ctrl2:
        load_btn = st.button("📥 Load Chart", key="m3_load", use_container_width=True)

    if not load_btn:
        st.info("Adjust the slider and click **Load Chart** to fetch live difficulty data.")
        return

    # ── Fetch data ─────────────────────────────────────────────────────────
    with st.spinner(f"Fetching {n_points} blocks of difficulty history…"):
        try:
            history = get_difficulty_history(n_points)
        except Exception as exc:
            st.error(f"⚠️ Failed to fetch difficulty history: {exc}")
            return

    if not history:
        st.warning("No data returned by the API.")
        return

    df = _build_dataframe(history)

    if df.empty or len(df) < 2:
        st.warning("Not enough data points to render the chart.")
        return

    # ── KPI metrics ────────────────────────────────────────────────────────
    latest_diff = df["difficulty"].iloc[-1]
    oldest_diff = df["difficulty"].iloc[0]
    pct_change = ((latest_diff - oldest_diff) / oldest_diff) * 100 if oldest_diff else 0
    date_range = f"{df['date'].iloc[0].strftime('%Y-%m-%d')}  →  {df['date'].iloc[-1].strftime('%Y-%m-%d')}"

    st.subheader("📊 Overview")
    kc1, kc2, kc3 = st.columns(3)
    kc1.metric("Latest Difficulty", f"{latest_diff / 1e12:.3f} T")
    kc2.metric("Change over period", f"{pct_change:+.1f}%")
    kc3.metric("Date range", date_range)

    st.divider()

    # ── Detect adjustment points ───────────────────────────────────────────
    adj_df = _detect_adjustment_points(df)

    # ── Main difficulty line chart ─────────────────────────────────────────
    st.subheader("📉 Difficulty Over Time")

    fig = go.Figure()

    # Main line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["difficulty"] / 1e12,
        mode="lines",
        name="Difficulty (T)",
        line=dict(color="#6366f1", width=2.5),
        hovertemplate=(
            "<b>%{x|%Y-%m-%d %H:%M}</b><br>"
            "Difficulty: %{y:.4f} T<extra></extra>"
        ),
    ))

    # Overlay adjustment event markers
    if not adj_df.empty:
        adj_valid = adj_df.dropna(subset=["ratio"])
        if not adj_valid.empty:
            marker_colors = [
                "#22c55e" if r >= 1.0 else "#ef4444"
                for r in adj_valid["ratio"]
            ]
            fig.add_trace(go.Scatter(
                x=adj_valid["date"],
                y=adj_valid["difficulty"] / 1e12,
                mode="markers",
                name="Difficulty adjustment",
                marker=dict(
                    size=11,
                    color=marker_colors,
                    symbol="diamond",
                    line=dict(color="#ffffff", width=1.2),
                ),
                hovertemplate=(
                    "<b>Adjustment event</b><br>"
                    "%{x|%Y-%m-%d}<br>"
                    "Difficulty: %{y:.4f} T<br>"
                    "Ratio (actual/target): %{customdata:.3f}<extra></extra>"
                ),
                customdata=adj_valid["ratio"],
            ))

            # Add vertical dashed lines at each adjustment
            for _, row in adj_valid.iterrows():
                fig.add_vline(
                    x=row["date"],
                    line_color="rgba(99,102,241,0.3)",
                    line_dash="dot",
                    line_width=1,
                )

    fig.update_layout(
        title=dict(
            text=(
                "Bitcoin Mining Difficulty — Historical Trend<br>"
                "<sup>Diamonds mark difficulty adjustment events (every ~2,016 blocks)</sup>"
            ),
            font=dict(size=15, color="#e2e8f0"),
        ),
        xaxis=dict(
            title="Date",
            gridcolor="rgba(255,255,255,0.07)",
            tickfont=dict(color="#e2e8f0"),
            title_font=dict(color="#e2e8f0"),
        ),
        yaxis=dict(
            title="Difficulty (Trillion, T)",
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
        height=450,
        margin=dict(l=10, r=10, t=90, b=50),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Adjustment ratio chart ─────────────────────────────────────────────
    if not adj_df.empty:
        adj_valid = adj_df.dropna(subset=["ratio"])
        if not adj_valid.empty:
            st.divider()
            st.subheader("⏱️ Block Time Ratio per Adjustment Epoch")
            st.markdown(
                "Shows whether miners found blocks **faster** (ratio < 1, 🔴) or "
                "**slower** (ratio > 1, 🟢) than the 10-minute target in each epoch. "
                "Bitcoin's algorithm corrects this deviation at each adjustment."
            )

            bar_colors = [
                "#22c55e" if r >= 1.0 else "#ef4444"
                for r in adj_valid["ratio"]
            ]

            fig2 = go.Figure()

            fig2.add_trace(go.Bar(
                x=adj_valid["date"],
                y=adj_valid["ratio"],
                name="Actual / Target time ratio",
                marker_color=bar_colors,
                opacity=0.85,
                hovertemplate=(
                    "<b>%{x|%Y-%m-%d}</b><br>"
                    "Ratio: %{y:.3f}<br>"
                    "Actual epoch ≈ %{customdata:.0f} s<extra></extra>"
                ),
                customdata=adj_valid["actual_epoch_s"],
            ))

            # Reference line at ratio = 1 (perfect 10-min blocks)
            fig2.add_hline(
                y=1.0,
                line_color="#f59e0b",
                line_dash="dash",
                line_width=2,
                annotation_text="Target (ratio = 1.0 → 10 min/block)",
                annotation_font_color="#f59e0b",
                annotation_position="top left",
            )

            fig2.update_layout(
                title=dict(
                    text=(
                        "Actual Block Time / Target Block Time per Epoch<br>"
                        "<sup>🟢 Slower than target  |  🔴 Faster than target</sup>"
                    ),
                    font=dict(size=15, color="#e2e8f0"),
                ),
                xaxis=dict(
                    title="Adjustment Date",
                    gridcolor="rgba(255,255,255,0.07)",
                    tickfont=dict(color="#e2e8f0"),
                    title_font=dict(color="#e2e8f0"),
                ),
                yaxis=dict(
                    title="Ratio (actual epoch time / target epoch time)",
                    gridcolor="rgba(255,255,255,0.07)",
                    tickfont=dict(color="#e2e8f0"),
                    title_font=dict(color="#e2e8f0"),
                    zeroline=False,
                ),
                height=360,
                margin=dict(l=10, r=10, t=90, b=50),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"),
                showlegend=False,
            )

            st.plotly_chart(fig2, use_container_width=True)

            # Ratio table
            with st.expander("📋 Adjustment events — detail table"):
                display_df = adj_valid[["date", "difficulty", "ratio", "actual_epoch_s"]].copy()
                display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d %H:%M UTC")
                display_df["difficulty"] = (display_df["difficulty"] / 1e12).round(4)
                display_df["ratio"] = display_df["ratio"].round(4)
                display_df["actual_epoch_s"] = display_df["actual_epoch_s"].round(0).astype("Int64")
                display_df.columns = ["Date", "Difficulty (T)", "Actual/Target Ratio", "Actual Epoch (s)"]
                st.dataframe(display_df, use_container_width=True, hide_index=True)

    with st.expander("📖 How does Bitcoin difficulty adjustment work?"):
        st.markdown(f"""
**Adjustment interval:** every **{EPOCH_BLOCKS:,} blocks** (~2 weeks at 10 min/block)

**Formula:**
```
new_difficulty = old_difficulty × (target_time / actual_time)
```
Where `target_time = {TARGET_EPOCH_TIME_S:,} seconds` (2 weeks).

- If miners found the last 2,016 blocks in **less than 2 weeks** (ratio < 1):
  difficulty **increases** → harder to mine.
- If miners took **more than 2 weeks** (ratio > 1):
  difficulty **decreases** → easier to mine.

The adjustment is capped at **±4×** per epoch to prevent runaway changes.

**Why?** Bitcoin's protocol guarantees a long-term average of ~10 minutes per block
regardless of changes in global hash rate (more miners joining, hardware improvements,
miners going offline, etc.).
""")
