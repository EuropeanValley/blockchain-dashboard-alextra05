"""
M5 — Merkle Proof Verifier: backend logic + Streamlit UI.

Bitcoin Merkle trees use double-SHA256 (SHA-256d):
    SHA256d(x) = SHA256(SHA256(x))

Byte-order convention:
    txids are displayed as big-endian hex strings, but the Merkle
    computation operates on their little-endian (reversed) byte form.
"""

import hashlib


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256d(data: bytes) -> bytes:
    """Return SHA-256d (double SHA-256) of data."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _hash_pair(left_hex: str, right_hex: str) -> str:
    """
    Concatenate two hashes (little-endian bytes) and return SHA-256d as
    a big-endian hex string, matching Bitcoin's Merkle construction.
    """
    # txids are stored/displayed big-endian; reverse each to get little-endian bytes
    left_bytes  = bytes.fromhex(left_hex)[::-1]   # big→little endian
    right_bytes = bytes.fromhex(right_hex)[::-1]  # big→little endian
    digest = _sha256d(left_bytes + right_bytes)
    return digest[::-1].hex()                      # little→big endian for display


# ---------------------------------------------------------------------------
# Public pure functions
# ---------------------------------------------------------------------------

def build_merkle_tree(txids: list[str]) -> list[list[str]]:
    """
    Build the full Merkle tree from a list of txids.

    Returns a list of levels, index 0 = leaf level (txids),
    last index = root level (single hash).

    If a level has an odd number of nodes, the last node is duplicated
    before hashing — this is the canonical Bitcoin rule.
    """
    if not txids:
        return []

    current_level = list(txids)  # copy; leaves are the raw txids
    tree: list[list[str]] = [current_level]

    while len(current_level) > 1:
        next_level: list[str] = []
        hashes = list(current_level)

        # Duplicate last hash when the count is odd (Bitcoin spec)
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        for i in range(0, len(hashes), 2):
            next_level.append(_hash_pair(hashes[i], hashes[i + 1]))

        tree.append(next_level)
        current_level = next_level

    return tree


def get_merkle_proof(txids: list[str], tx_index: int) -> list[dict]:
    """
    Return the Merkle proof path for the transaction at tx_index.

    Each proof step is a dict:
        { "hash": <sibling_hash_hex>, "position": "left" | "right" }

    "position" indicates where the *sibling* sits relative to the
    current node, which tells the verifier whether to place the
    sibling on the left or right during each hash step.
    """
    tree = build_merkle_tree(txids)
    proof: list[dict] = []
    index = tx_index  # tracks position of our node within the current level

    # Walk up every level except the root
    for level in tree[:-1]:
        hashes = list(level)

        # Duplicate last hash when odd — must mirror build_merkle_tree exactly
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        if index % 2 == 0:
            # current node is a left child → sibling is to the right
            sibling = hashes[index + 1]
            proof.append({"hash": sibling, "position": "right"})
        else:
            # current node is a right child → sibling is to the left
            sibling = hashes[index - 1]
            proof.append({"hash": sibling, "position": "left"})

        index //= 2  # move up one level

    return proof


def verify_merkle_proof(txid: str, proof: list[dict], merkle_root: str) -> bool:
    """
    Verify a Merkle proof for txid against a known merkle_root.

    Recomputes the root by hashing the txid with each proof step
    in order and returns True iff the final hash equals merkle_root.
    """
    current = txid  # start from the transaction's own hash

    for step in proof:
        sibling  = step["hash"]
        position = step["position"]

        if position == "left":
            # sibling is on the left → hash(sibling || current)
            current = _hash_pair(sibling, current)
        else:
            # sibling is on the right → hash(current || sibling)
            current = _hash_pair(current, sibling)

    return current == merkle_root


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

import math
import plotly.graph_objects as go
import streamlit as st

from api.blockchain_client import (
    get_block,
    get_block_transactions,
    get_tip_hash,
)

# dark-theme palette shared with other modules
_BG       = "rgba(0,0,0,0)"
_FONT     = "#e2e8f0"
_PRIMARY  = "#6366f1"
_GRID     = "rgba(255,255,255,0.07)"
_CARD_CSS = (
    "background:rgba(255,255,255,0.05);"
    "border:1px solid rgba(255,255,255,0.08);"
    "border-radius:12px;padding:16px;"
)


def _trunc(h: str, n: int = 12) -> str:
    """Return first n + last n chars of a hash with … in the middle."""
    return f"{h[:n]}…{h[-n:]}" if len(h) > 2 * n else h


def _build_tree_figure(tree: list[list[str]], tx_index: int) -> go.Figure:
    """Return a Plotly figure showing the Merkle tree top-down."""
    if not tree:
        return go.Figure()

    n_levels = len(tree)
    node_x, node_y, node_text, node_color = [], [], [], []
    edge_x, edge_y = [], []

    # Map (level, pos) → (x, y) coordinates
    coords: dict[tuple[int, int], tuple[float, float]] = {}

    for lvl_idx, level in enumerate(tree):
        # level 0 = leaves (bottom); root is at top
        y = (n_levels - 1 - lvl_idx) / max(n_levels - 1, 1)
        n_nodes = len(level)
        for pos, h in enumerate(level):
            x = (pos + 0.5) / n_nodes
            coords[(lvl_idx, pos)] = (x, y)

            # highlight the path from chosen tx up to root
            is_path = False
            path_pos = tx_index
            for k in range(lvl_idx + 1):
                if k == lvl_idx and path_pos == pos:
                    is_path = True
                    break
                path_pos //= 2

            color = _PRIMARY if is_path else "rgba(100,116,139,0.6)"
            node_x.append(x)
            node_y.append(y)
            node_text.append(_trunc(h, 8))
            node_color.append(color)

    # Draw edges level → level+1
    for lvl_idx, level in enumerate(tree[:-1]):
        hashes = list(level)
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])   # mirror the duplication rule
        for pos in range(0, len(hashes), 2):
            parent_pos = pos // 2
            cx, cy = coords[(lvl_idx, min(pos,     len(tree[lvl_idx]) - 1))]
            dx, dy = coords[(lvl_idx, min(pos + 1, len(tree[lvl_idx]) - 1))]
            px, py = coords[(lvl_idx + 1, parent_pos)]
            # left child → parent
            edge_x += [cx, px, None]
            edge_y += [cy, py, None]
            # right child → parent
            edge_x += [dx, px, None]
            edge_y += [dy, py, None]

    fig = go.Figure()

    # Edges
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(color="rgba(148,163,184,0.35)", width=1),
        hoverinfo="skip",
        showlegend=False,
    ))

    # Nodes
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont=dict(size=9, color=_FONT),
        marker=dict(size=14, color=node_color, line=dict(width=1, color=_FONT)),
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(
            text="🌿 Merkle Tree — highlighted path from selected tx to root",
            font=dict(size=14, color=_FONT),
        ),
        xaxis=dict(
            title="Position within level (normalised)",
            showgrid=False, zeroline=False,
            tickfont=dict(color=_FONT),
            title_font=dict(color=_FONT),
        ),
        yaxis=dict(
            title="Tree level (0 = root, bottom = leaves)",
            showgrid=False, zeroline=False,
            tickfont=dict(color=_FONT),
            title_font=dict(color=_FONT),
        ),
        height=420,
        margin=dict(l=10, r=10, t=60, b=60),
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color=_FONT),
    )
    return fig


def render() -> None:
    """Render the complete M5 — Merkle Proof Verifier panel."""
    st.header("🌿  M5 — Merkle Proof Verifier")
    st.markdown(
        "Select a Bitcoin block, pick a transaction, and verify its "
        "**Merkle inclusion proof** step by step.  \n"
        "Data source: [Blockstream API](https://blockstream.info/api/)"
    )

    # ── Block selection ────────────────────────────────────────────────────
    st.subheader("Block selection")
    mode = st.radio(
        "Block source",
        ["Latest block", "Enter block hash manually"],
        horizontal=True,
        key="m5_mode",
    )

    block_hash = ""
    if mode == "Latest block":
        with st.spinner("Fetching chain tip…"):
            try:
                block_hash = get_tip_hash()
                st.caption(f"Latest block hash: `{block_hash}`")
            except Exception as exc:
                st.error(f"⚠️ Could not fetch chain tip: {exc}")
                return
    else:
        block_hash = st.text_input(
            "Block hash (64 hex chars)",
            placeholder="000000000000000000…",
            key="m5_block_hash",
        ).strip()
        if not block_hash:
            st.info("Enter a block hash and click **Compute Proof**.")
            return

    # ── Load block header + tx list ────────────────────────────────────────
    with st.spinner("Loading block data…"):
        try:
            block_data = get_block(block_hash)
            txids      = get_block_transactions(block_hash)
        except Exception as exc:
            st.error(f"⚠️ Failed to load block: {exc}")
            return

    if not txids:
        st.warning("No transactions found in this block.")
        return

    merkle_root = block_data.get("merkle_root", "")
    tx_count    = len(txids)

    # Metrics row
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Block Height",    block_data.get("height", "—"))
    mc2.metric("Transactions",    tx_count)
    mc3.metric("Merkle Root",     _trunc(merkle_root, 10))

    st.divider()

    # ── Transaction selector ───────────────────────────────────────────────
    st.subheader("Transaction selector")
    preview_txids = txids[:10]  # show only first 10 to keep UI compact
    options       = [f"[{i}] {_trunc(t)}" for i, t in enumerate(preview_txids)]
    chosen_label  = st.selectbox(
        "Choose a transaction (first 10 shown)",
        options,
        key="m5_tx_select",
    )
    tx_index = options.index(chosen_label)   # index within preview == index in full list
    chosen_txid = txids[tx_index]

    st.caption(f"Full txid: `{chosen_txid}`")

    run = st.button("🔍 Compute Proof", key="m5_run", use_container_width=False)
    if not run:
        st.info("Click **Compute Proof** to generate and verify the Merkle proof.")
        return

    # ── Compute proof ──────────────────────────────────────────────────────
    try:
        proof   = get_merkle_proof(txids, tx_index)
        valid   = verify_merkle_proof(chosen_txid, proof, merkle_root)
        tree    = build_merkle_tree(txids)

        # Recompute root from proof to show the computed value
        current = chosen_txid
        for step in proof:
            if step["position"] == "left":
                current = _hash_pair(step["hash"], current)
            else:
                current = _hash_pair(current, step["hash"])
        computed_root = current
    except Exception as exc:
        st.error(f"⚠️ Proof computation failed: {exc}")
        return

    st.divider()

    # ── Verification result ────────────────────────────────────────────────
    st.subheader("Verification result")
    if valid:
        st.success(f"✅ Proof is **VALID** — computed root matches the block's merkle_root.")
    else:
        st.error(f"❌ Proof is **INVALID** — computed root does NOT match the block's merkle_root.")

    res_col1, res_col2 = st.columns(2)
    res_col1.text_input("Expected merkle_root",  value=merkle_root,    key="m5_exp_root",  disabled=True)
    res_col2.text_input("Computed merkle_root",  value=computed_root,  key="m5_comp_root", disabled=True)

    st.divider()

    # ── Proof steps table ──────────────────────────────────────────────────
    st.subheader("Proof steps")
    if not proof:
        st.info("This block has only one transaction — no siblings needed; root == txid.")
    else:
        rows = [
            {
                "Step":     i + 1,
                "Sibling Hash": step["hash"],
                "Position": step["position"].upper(),
            }
            for i, step in enumerate(proof)
        ]
        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Step":          st.column_config.NumberColumn("Step",          width="small"),
                "Sibling Hash":  st.column_config.TextColumn("Sibling Hash",    width="large"),
                "Position":      st.column_config.TextColumn("Position",        width="small"),
            },
        )

    st.divider()

    # ── Merkle tree diagram ────────────────────────────────────────────────
    st.subheader("Visual Merkle tree")
    st.caption("Purple nodes = proof path from selected tx to the root.")
    try:
        fig = _build_tree_figure(tree, tx_index)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.warning(f"Could not render tree diagram: {exc}")
