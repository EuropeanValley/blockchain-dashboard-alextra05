"""
M5 — Merkle Proof Verifier (backend logic only, no Streamlit).

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
