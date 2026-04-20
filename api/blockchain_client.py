"""
Blockchain API client.

Provides helper functions to fetch blockchain data from public APIs.
"""

import requests

BASE_URL = "https://blockstream.info/api"


def get_latest_block_hash() -> str:
    """Return latest Bitcoin block hash."""
    response = requests.get(f"{BASE_URL}/blocks/tip/hash", timeout=10)
    response.raise_for_status()
    return response.text.strip()


def get_latest_block() -> dict:
    """Return latest Bitcoin block data."""
    block_hash = get_latest_block_hash()
    return get_block(block_hash)


def get_block(block_hash: str) -> dict:
    """Return full details for a block identified by block_hash."""
    response = requests.get(f"{BASE_URL}/block/{block_hash}", timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    block = get_latest_block()

    print("block height:", block["height"])
    print("hash:", block["id"])
    print("difficulty:", block["difficulty"])
    print("nonce:", block["nonce"])
    print("number of transactions:", block["tx_count"])

    # The block hash starts with leading zeros because miners must
    # find a hash below the Proof of Work target.
    # The bits field stores that target in compact format.