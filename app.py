"""
Blockchain Dashboard — main Streamlit entry point.

Renders four tabbed modules:
  M1 — Proof of Work Monitor  (live Bitcoin PoW data)
  M2 — Block Header Analyzer  (inspect individual block headers)
  M3 — Difficulty History     (difficulty adjustment over time)
  M4 — AI Component           (AI/ML analysis placeholder)

Auto-refreshes the M1 tab every 60 seconds using st.rerun().
"""

import time

import streamlit as st

# ── Page config must be the very first Streamlit call ─────────────────────
st.set_page_config(
    page_title="Bitcoin Blockchain Dashboard",
    page_icon="⛓️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Module imports (each module exposes a render() function) ──────────────
from modules.m1_pow_monitor import render as render_m1
from modules.m2_block_header import render as render_m2
from modules.m3_difficulty_history import render as render_m3
from modules.m4_ai_component import render as render_m4

# ── Custom CSS for a polished dark-themed look ────────────────────────────
st.markdown("""
<style>
  /* Global dark background */
  [data-testid="stAppViewContainer"] {
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  }
  [data-testid="stHeader"] { background: transparent; }

  /* Tab styling */
  .stTabs [data-baseweb="tab-list"] {
      gap: 8px;
      background-color: rgba(255,255,255,0.04);
      border-radius: 12px;
      padding: 6px;
  }
  .stTabs [data-baseweb="tab"] {
      border-radius: 8px;
      color: #94a3b8;
      font-weight: 500;
      padding: 8px 20px;
  }
  .stTabs [aria-selected="true"] {
      background-color: #6366f1 !important;
      color: #ffffff !important;
  }

  /* Metric cards */
  [data-testid="stMetric"] {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 16px;
  }
  [data-testid="stMetricValue"] { font-size: 1.5rem !important; }

  /* Divider */
  hr { border-color: rgba(255,255,255,0.08) !important; }

  /* Header */
  h1, h2, h3 { color: #f1f5f9 !important; }
</style>
""", unsafe_allow_html=True)

# ── Dashboard header ───────────────────────────────────────────────────────
st.title("⛓️  Bitcoin Blockchain Dashboard")
st.markdown(
    "Real-time analysis of the Bitcoin network · "
    "Data source: [Blockstream API](https://blockstream.info/api/)"
)

# ── Auto-refresh countdown (only meaningful on the M1 tab) ────────────────
REFRESH_INTERVAL = 60  # seconds

# We store the timestamp of the last refresh in session state so that the
# countdown is consistent across reruns triggered by other widget interactions.
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = time.time()

elapsed = time.time() - st.session_state["last_refresh"]
seconds_left = max(0, int(REFRESH_INTERVAL - elapsed))

refresh_col, spacer = st.columns([2, 8])
with refresh_col:
    st.caption(f"🔄 Auto-refresh in **{seconds_left}s** · every {REFRESH_INTERVAL}s")
    if st.button("↺ Refresh now", key="manual_refresh"):
        st.session_state["last_refresh"] = time.time()
        st.rerun()

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "⛏️  M1 — PoW Monitor",
    "🔍  M2 — Block Header",
    "📈  M3 — Difficulty History",
    "🤖  M4 — AI Component",
])

with tab1:
    try:
        render_m1()
    except Exception as exc:
        st.error(f"⚠️ M1 crashed unexpectedly: {exc}")
        st.exception(exc)

with tab2:
    try:
        render_m2()
    except Exception as exc:
        st.error(f"⚠️ M2 crashed unexpectedly: {exc}")
        st.exception(exc)

with tab3:
    try:
        render_m3()
    except Exception as exc:
        st.error(f"⚠️ M3 crashed unexpectedly: {exc}")
        st.exception(exc)

with tab4:
    try:
        render_m4()
    except Exception as exc:
        st.error(f"⚠️ M4 crashed unexpectedly: {exc}")
        st.exception(exc)

# ── Auto-refresh loop ──────────────────────────────────────────────────────
# Sleep until the next 60-second boundary, then trigger a full page rerun.
# st.rerun() replaces the deprecated st.experimental_rerun().
if elapsed >= REFRESH_INTERVAL:
    st.session_state["last_refresh"] = time.time()
    time.sleep(0.1)   # brief pause to avoid tight-loop in edge cases
    st.rerun()
else:
    # Sleep only the remaining time; Streamlit will re-execute the script
    # after the sleep completes, which updates the countdown and refreshes data.
    time.sleep(seconds_left if seconds_left > 0 else REFRESH_INTERVAL)
    st.session_state["last_refresh"] = time.time()
    st.rerun()
