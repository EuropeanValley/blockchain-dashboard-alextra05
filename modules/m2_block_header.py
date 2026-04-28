"""
M2 — Block Header Analyzer
===========================
Fetches a Bitcoin block, parses its 80-byte header (all fields little-endian),
computes SHA-256d via hashlib, and verifies the PoW constraint (hash < target).
"""

import hashlib
import struct
import datetime

import streamlit as st
import requests

from api.blockchain_client import get_latest_block, BASE_URL, TIMEOUT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_raw_header(block_hash: str) -> str:
    """Return the 80-byte block header as a hex string from Blockstream."""
    url = f"{BASE_URL}/block/{block_hash}/header"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text.strip()


def _parse_header(raw_hex: str) -> dict:
    """
    Parse the 80-byte little-endian header and return a dict of decoded fields.

    All uint32 fields are parsed with struct.unpack('<I', ...) — the '<' prefix
    means little-endian, 'I' means unsigned 32-bit integer.

    Hash fields (prev_hash, merkle_root) are 32-byte sequences stored in LE;
    to obtain the conventional big-endian hex string used by block explorers
    we reverse the bytes before hex-encoding.
    """
    raw = bytes.fromhex(raw_hex)
    assert len(raw) == 80, f"Expected 80 bytes, got {len(raw)}"

    # version: bytes 0-3, LE uint32
    version = struct.unpack("<I", raw[0:4])[0]

    # prev_hash: bytes 4-35, 32 bytes LE → reverse for display
    prev_hash = raw[4:36][::-1].hex()

    # merkle_root: bytes 36-67, 32 bytes LE → reverse for display
    merkle_root = raw[36:68][::-1].hex()

    # timestamp: bytes 68-71, LE uint32 → convert to human-readable UTC
    timestamp_raw = struct.unpack("<I", raw[68:72])[0]
    timestamp_human = datetime.datetime.utcfromtimestamp(timestamp_raw).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    # bits: bytes 72-75, LE uint32 (compact target)
    bits = struct.unpack("<I", raw[72:76])[0]

    # nonce: bytes 76-79, LE uint32
    nonce = struct.unpack("<I", raw[76:80])[0]

    return {
        "version": version,
        "prev_hash": prev_hash,
        "merkle_root": merkle_root,
        "timestamp_raw": timestamp_raw,
        "timestamp_human": timestamp_human,
        "bits": bits,
        "nonce": nonce,
    }


def _sha256d(data: bytes) -> bytes:
    """Compute SHA-256(SHA-256(data)) — Bitcoin's double-hash."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _bits_to_target(bits: int) -> int:
    """Convert compact 'bits' field to the full 256-bit target integer."""
    exponent = (bits >> 24) & 0xFF    # top byte: byte-length of target
    coefficient = bits & 0x00FFFFFF   # lower 3 bytes: significant digits
    byte_shift = exponent - 3         # T = coefficient × 256^(exponent-3)
    if byte_shift >= 0:
        return coefficient << (byte_shift * 8)
    else:
        return coefficient >> ((-byte_shift) * 8)


def _count_leading_zero_bits(hash_bytes: bytes) -> int:
    """Count the number of leading zero BITS in a 32-byte hash."""
    count = 0
    for byte in hash_bytes:
        if byte == 0:
            count += 8
        else:
            # popcount approach: count leading zeros in this byte
            for bit in range(7, -1, -1):
                if byte & (1 << bit):
                    return count
                count += 1
            break
    return count


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the complete M2 — Block Header Analyzer panel."""
    st.header("🔍  M2 — Block Header Analyzer")
    st.markdown(
        "Inspect the 80-byte Bitcoin block header, verify the Proof-of-Work "
        "constraint via SHA-256d, and explore all canonical header fields.  \n"
        "Data source: [Blockstream API](https://blockstream.info/api/)"
    )

    # ── Mode selector ──────────────────────────────────────────────────────
    mode = st.radio(
        "Block source",
        ["Latest block (auto)", "Enter block hash manually"],
        horizontal=True,
        key="m2_mode",
    )

    block_hash_input = ""
    if mode == "Enter block hash manually":
        block_hash_input = st.text_input(
            "Block hash (hex)",
            placeholder="000000000000000000…",
            key="m2_hash_input",
        )

    analyze_btn = st.button("🔬 Analyze Block Header", key="m2_analyze")

    if not analyze_btn:
        st.info("Select a block source and click **Analyze Block Header** to begin.")
        return

    # ── Data fetching ──────────────────────────────────────────────────────
    with st.spinner("Fetching block data from Blockstream…"):
        try:
            if mode == "Latest block (auto)" or not block_hash_input.strip():
                block = get_latest_block()
            else:
                from api.blockchain_client import get_block
                block = get_block(block_hash_input.strip())

            block_hash = block["id"]
            raw_header_hex = _fetch_raw_header(block_hash)

        except Exception as exc:
            st.error(f"⚠️ Failed to fetch block data: {exc}")
            return

    # ── Parse header ───────────────────────────────────────────────────────
    try:
        fields = _parse_header(raw_header_hex)
    except Exception as exc:
        st.error(f"⚠️ Failed to parse 80-byte header: {exc}")
        return

    st.divider()

    # ── KPI row ────────────────────────────────────────────────────────────
    st.subheader("📦 Block Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Block Height", f"{block.get('height', 'N/A'):,}" if isinstance(block.get('height'), int) else "N/A")
    c2.metric("Tx Count", f"{block.get('tx_count', 'N/A'):,}" if isinstance(block.get('tx_count'), int) else "N/A")
    c3.metric("Size (bytes)", f"{block.get('size', 'N/A'):,}" if isinstance(block.get('size'), int) else "N/A")
    c4.metric("Weight (WU)", f"{block.get('weight', 'N/A'):,}" if isinstance(block.get('weight'), int) else "N/A")

    st.divider()

    # ── 6-field header table ───────────────────────────────────────────────
    st.subheader("📋 80-Byte Block Header — All 6 Fields")
    st.caption(
        "⚠️ **Little-endian note:** multi-byte integers in the raw header bytes are "
        "stored in little-endian (LE) byte order. Hash fields are byte-reversed "
        "before display to match the big-endian convention used by block explorers."
    )

    header_data = {
        "Field": [
            "Version",
            "Previous Block Hash",
            "Merkle Root",
            "Timestamp",
            "Bits (compact target)",
            "Nonce",
        ],
        "Offset (bytes)": ["0–3", "4–35", "36–67", "68–71", "72–75", "76–79"],
        "Size": ["4 B", "32 B", "32 B", "4 B", "4 B", "4 B"],
        "Value": [
            f"0x{fields['version']:08x}  (v{fields['version']})",
            fields["prev_hash"],
            fields["merkle_root"],
            f"{fields['timestamp_human']}  (Unix: {fields['timestamp_raw']})",
            f"0x{fields['bits']:08x}",
            f"{fields['nonce']:,}  (0x{fields['nonce']:08x})",
        ],
    }

    import pandas as pd
    df_header = pd.DataFrame(header_data)
    st.dataframe(
        df_header,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Field": st.column_config.TextColumn("Field", width="medium"),
            "Offset (bytes)": st.column_config.TextColumn("Offset", width="small"),
            "Size": st.column_config.TextColumn("Size", width="small"),
            "Value": st.column_config.TextColumn("Value", width="large"),
        },
    )

    st.divider()

    # ── Raw hex ────────────────────────────────────────────────────────────
    with st.expander("🧮 Raw 80-byte header (hex)"):
        st.code(raw_header_hex, language=None)
        st.caption(
            "Bytes are in their native little-endian order as transmitted on the "
            "Bitcoin P2P network and hashed by miners."
        )

    st.divider()

    # ── SHA-256d PoW Verification ──────────────────────────────────────────
    st.subheader("🔐 SHA-256d Proof-of-Work Verification")
    st.markdown(
        "We manually compute **SHA-256(SHA-256(header_bytes))** using Python's "
        "`hashlib` and verify the result is numerically below the target derived "
        "from the `bits` field."
    )

    raw_header_bytes = bytes.fromhex(raw_header_hex)
    computed_hash_bytes = _sha256d(raw_header_bytes)
    # Bitcoin displays the hash byte-reversed (big-endian)
    computed_hash_hex = computed_hash_bytes[::-1].hex()

    target = _bits_to_target(fields["bits"])
    hash_int = int.from_bytes(computed_hash_bytes[::-1], "big")  # interpret as big-endian uint256
    pow_valid = hash_int < target

    leading_zero_bits = _count_leading_zero_bits(computed_hash_bytes[::-1])

    # Show computed vs. expected hash
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Computed hash (SHA-256d of raw header):**")
        st.code(computed_hash_hex, language=None)
    with col_b:
        st.markdown("**Known block hash (from API):**")
        st.code(block_hash, language=None)

    match = computed_hash_hex == block_hash
    if match:
        st.success("✅ Computed hash **matches** the API-reported block hash — header bytes are correct.")
    else:
        st.error("❌ Hash mismatch — header bytes may have been altered or the API returned unexpected data.")

    st.divider()

    # PoW threshold check
    col1, col2, col3 = st.columns(3)
    col1.metric("Leading Zero Bits", leading_zero_bits)
    col2.metric("Target (hex, truncated)", f"0x{target:064x}"[:20] + "…")
    col3.metric("Hash < Target?", "✅ YES" if pow_valid else "❌ NO")

    if pow_valid:
        st.success(
            f"✅ **Valid Proof-of-Work** — the block hash is numerically **below** the target.  \n"
            f"Hash has **{leading_zero_bits} leading zero bits**, satisfying the difficulty requirement."
        )
    else:
        st.error(
            "❌ **Invalid Proof-of-Work** — the computed hash exceeds the target. "
            "This should not happen for a confirmed block."
        )

    with st.expander("🔢 SHA-256d step-by-step"):
        first_hash = hashlib.sha256(raw_header_bytes).digest()
        st.markdown(f"""
**Step 1 — SHA-256(header_bytes):**
```
{first_hash.hex()}
```

**Step 2 — SHA-256(result of step 1):**
```
{computed_hash_bytes.hex()}
```

**Step 3 — Byte-reverse (little-endian → big-endian display):**
```
{computed_hash_hex}
```

**Target (from `bits = 0x{fields['bits']:08x}`):**
```
{target:064x}
```

**Hash as integer < Target?** → {"✅ YES — valid PoW" if pow_valid else "❌ NO"}
        """)
