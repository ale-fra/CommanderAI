"""Card catalog loading with an in-process cache.

The oracle file is parsed once per (path, mtime, size). The CLI loads it once
per command anyway; the API server reuses the parsed index across requests.
``Card`` objects are never mutated by the deck builder, so sharing is safe.
"""

from __future__ import annotations

import threading
from pathlib import Path

from commanderai.data.card_index import CardIndex
from commanderai.data.scryfall import load_catalog_data
from commanderai.errors import CatalogNotFoundError

_lock = threading.Lock()
_cache: dict[tuple[str, int, int], CardIndex] = {}


def load_catalog(path: Path, use_cache: bool = True) -> CardIndex:
    """Return the CardIndex for an oracle_cards.json file."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        raise CatalogNotFoundError(
            f"Oracle cards not found at {path}. Run 'commanderai update-data' first.",
            path=str(path),
        ) from None

    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if use_cache:
        with _lock:
            cached = _cache.get(key)
        if cached is not None:
            return cached

    cards, non_legal = load_catalog_data(path)
    index = CardIndex(cards, non_legal_names=non_legal)
    if use_cache:
        with _lock:
            _cache.clear()  # only ever keep the current snapshot
            _cache[key] = index
    return index


def clear_cache() -> None:
    with _lock:
        _cache.clear()
