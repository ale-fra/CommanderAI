"""Deck text files on disk: naming and writing exports.

Text files are export artifacts only; the deck database
(:mod:`commanderai.services.library`) is the single source of truth.
"""

from __future__ import annotations

import re
from pathlib import Path

from commanderai.models import Deck
from commanderai.output.export import export_deck
from commanderai.output.formatter import format_deck


def safe_deck_name(commander_name: str) -> str:
    return re.sub(r"[^\w\-]", "_", commander_name.split("//")[0].strip()).lower().strip("_")


def next_deck_path(decks_dir: Path, commander_name: str, ext: str = "txt") -> Path:
    """``decks/<commander>.txt``, or ``<commander>_N.txt`` — never overwrites."""
    decks_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_deck_name(commander_name)
    output = decks_dir / f"{safe_name}.{ext}"
    counter = 1
    while output.exists():
        counter += 1
        output = decks_dir / f"{safe_name}_{counter}.{ext}"
    return output


def render_deck(deck: Deck, fmt: str = "text", verbose: bool = False) -> str:
    """Deck as text: grouped human-readable format for 'text', else an export format."""
    return export_deck(deck, fmt) if fmt != "text" else format_deck(deck, verbose)


def write_deck_file(deck: Deck, path: Path, fmt: str = "text", verbose: bool = False) -> Path:
    path.write_text(render_deck(deck, fmt, verbose))
    return path
