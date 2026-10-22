"""Lightweight shared contract for admin-only cached population MDA.

Do not import offline analyzers from web request handlers.
"""
from __future__ import annotations

FORMAT = "mda-admin-cache-v1"
MAX_DOC_BYTES = 50_000

# Tiny immutable copy of positional scopes, validated against the actual MDA
# ranges module by the release-gated contract test. Keeps app startup light.
POSITIONS_BY_SIZE = {
    2: ("BTN/SB", "BB"),
    3: ("BTN", "SB", "BB"),
    4: ("BTN", "SB", "BB", "CO"),
    5: ("BTN", "SB", "BB", "UTG", "CO"),
    6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
}


def cache_key(game: str, table_size: int, position: str) -> str:
    """Only allow anonymous game / actual dealt-in size / position keys."""
    if game not in ("Ring", "Sit&Go"):
        raise ValueError("MDA population format must be Ring or Sit&Go")
    if type(table_size) is not int or position not in POSITIONS_BY_SIZE.get(table_size, ()):
        raise ValueError("invalid dealt-in table size / position")
    return f"{game}:{table_size}:{position}"
