"""
Blockchain API client — Blockstream.info (no API key required).

Provides helper functions to fetch live Bitcoin network data.
All endpoints are documented at: https://blockstream.info/api/
"""

import time
import requests

BASE_URL = "https://blockstream.info/api"
TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> requests.Response:
    """HTTP GET with unified timeout and raise-on-error."""
    time.sleep(0.3)  # avoid rate limiting (Blockstream: ~3 req/s)
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_tip_height() -> int:
    """Return the current best block height (chain tip)."""
    return int(_get(f"{BASE_URL}/blocks/tip/height").text.strip())


def get_tip_hash() -> str:
    """Return the block hash of the chain tip."""
    return _get(f"{BASE_URL}/blocks/tip/hash").text.strip()


def get_block(block_hash: str) -> dict:
    """
    Return full header data for a single block identified by its hash.

    Relevant fields returned by Blockstream:
        id          – block hash (hex string)
        height      – block height in the chain
        timestamp   – Unix timestamp (seconds since epoch)
        difficulty  – current network difficulty (float)
        bits        – compact target representation (uint32, little-endian encoding)
        nonce       – 32-bit nonce miners iterated over (uint32)
        tx_count    – number of transactions in the block
        size        – block size in bytes
        weight      – block weight in weight units
    """
    return _get(f"{BASE_URL}/block/{block_hash}").json()


def get_latest_block() -> dict:
    """Fetch the very latest Bitcoin block (height + hash + full header)."""
    return get_block(get_tip_hash())


def get_block_at_height(height: int) -> dict:
    """Return the first block at a given height."""
    blocks = _get(f"{BASE_URL}/blocks/{height}").json()
    # element 0 is the canonical block at the requested height
    return blocks[0]


def get_recent_block_timestamps(n: int = 50) -> list[int]:
    """Return Unix timestamps for the most recent n blocks (descending order)."""
    timestamps: list[int] = []
    tip_height = get_tip_height()
    current_height = tip_height

    while len(timestamps) < n:
        blocks = _get(f"{BASE_URL}/blocks/{current_height}").json()
        if not blocks:
            break
        for block in blocks:
            timestamps.append(block["timestamp"])
            if len(timestamps) >= n:
                break
        current_height -= len(blocks)

    return timestamps[:n]


def get_hashrate() -> float:
    """
    Estimate the current network hash rate (hashes/second).
    Formula: hash_rate ≈ difficulty × 2^32 / 600
    """
    latest = get_latest_block()
    difficulty = float(latest["difficulty"])
    hashrate_hs = difficulty * (2 ** 32) / 600  # H = D × 2³² / 600 s
    return hashrate_hs


# ---------------------------------------------------------------------------
# M3 compatibility: difficulty history
# ---------------------------------------------------------------------------

def get_difficulty_history(n_points: int = 100) -> list[dict]:
    """Return a list of {x: timestamp, y: difficulty} for the last n_points blocks."""
    tip_height = get_tip_height()
    result: list[dict] = []
    current_height = tip_height

    while len(result) < n_points and current_height > 0:
        blocks = _get(f"{BASE_URL}/blocks/{current_height}").json()
        if not blocks:
            break
        for block in blocks:
            result.append({
                "x": block["timestamp"],
                "y": block["difficulty"],
            })
            if len(result) >= n_points:
                break
        current_height -= len(blocks)

    return list(reversed(result[:n_points]))


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    block = get_latest_block()
    print("Block height   :", block["height"])
    print("Block hash     :", block["id"])
    print("Difficulty     :", block["difficulty"])
    print("Bits (compact) :", hex(block["bits"]))
    print("Nonce          :", block["nonce"])
    print("Tx count       :", block["tx_count"])
    print("Timestamp      :", block["timestamp"])

    ts = get_recent_block_timestamps(10)
    print("\nLast 10 block timestamps:", ts)

    hr = get_hashrate()
    print(f"\nEstimated hash rate: {hr / 1e18:.3f} EH/s")