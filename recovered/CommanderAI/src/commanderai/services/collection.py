"""Collection / decklist loading, matching against the catalog, and conversion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from commanderai.collection.matcher import MatchResult, get_unique_cards, match_collection
from commanderai.collection.parser import aggregate_entries, convert_to_text, parse_collection
from commanderai.errors import CollectionNotFoundError, EmptyCollectionError
from commanderai.models import Card, CollectionEntry, PublicModel
from commanderai.services.context import ServiceContext


class FuzzyMatch(PublicModel):
    original: str
    corrected: str


class MatchReport(PublicModel):
    """Serializable summary of how a collection/decklist matched the catalog."""

    source: str
    entries: int = 0                      # parsed lines
    copies: int = 0                       # sum of quantities over parsed lines
    matched: int = 0                      # lines matched to a card
    matched_copies: int = 0
    unique_cards: int = 0                 # distinct matched cards
    fuzzy: list[FuzzyMatch] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)  # tokens / special cards


@dataclass
class LoadedCollection:
    source: str
    entries: list[CollectionEntry]
    match: MatchResult
    cards: list[Card]          # unique matched cards, in collection order
    report: MatchReport

    @property
    def owned_names(self) -> set[str]:
        return {c.name for c in self.cards}


def require_file(path: Path, kind: str = "Collection") -> None:
    if not path.exists():
        raise CollectionNotFoundError(f"{kind} file not found: {path}", path=str(path), kind=kind.lower())


def _source_label(source: Path | str) -> str:
    return str(source) if isinstance(source, Path) else "<text>"


def parse_source(source: Path | str) -> list[CollectionEntry]:
    """Parse a file (Path) or raw text (str) into collection entries."""
    return parse_collection(source)


def build_report(source: str, entries: list[CollectionEntry], match: MatchResult,
                 cards: list[Card]) -> MatchReport:
    return MatchReport(
        source=source,
        entries=len(entries),
        copies=sum(e.quantity for e in entries),
        matched=len(match.matched),
        matched_copies=sum(e.quantity for e in match.matched),
        unique_cards=len(cards),
        fuzzy=[FuzzyMatch(original=o, corrected=c) for o, c in match.fuzzy_matched],
        unmatched=list(match.unmatched),
        skipped=list(match.skipped_tokens),
    )


def load_collection(
    ctx: ServiceContext,
    source: Path | str,
    *,
    kind: str = "Collection",
    check_exists: bool = True,
    empty_message: str | None = None,
    label: str | None = None,
) -> LoadedCollection:
    """Load + match a collection or decklist.

    Order of operations (file check → catalog load → parse → empty check →
    match) mirrors the historical CLI so messages appear in the same order.

    - ``source``: a file path, or the raw text of a list.
    - ``empty_message``: if given, raise EmptyCollectionError with it when the
      source contains no card lines.
    - ``label``: how to describe the source in reports (default: the path, or
      ``<text>`` for raw text).
    """
    if check_exists and isinstance(source, Path):
        require_file(source, kind)
    index = ctx.catalog()
    entries = parse_source(source)
    source_label = label or _source_label(source)
    if not entries and empty_message:
        raise EmptyCollectionError(empty_message, source=source_label)
    match = match_collection(entries, index)
    cards = get_unique_cards(match.matched)
    return LoadedCollection(
        source=source_label,
        entries=entries,
        match=match,
        cards=cards,
        report=build_report(source_label, entries, match, cards),
    )


def resolve_collection_source(
    ctx: ServiceContext,
    path: Path | None = None,
    text: str | None = None,
    collection_id: int | None = None,
) -> tuple[Path | str, str | None]:
    """Pick the collection source of a request: stored collection id, raw text,
    explicit path, or the configured default collection. Returns (source, label)."""
    if collection_id is not None:
        from commanderai.services.collections import get_collection

        stored = get_collection(ctx, collection_id)
        return stored.content or "", f"collection:#{stored.id} {stored.name}"
    if text is not None:
        return text, None
    return path or ctx.settings.default_collection, None


class ConvertResult(BaseModel):
    text: str
    unique_cards: int
    total_cards: int


def convert_collection(source: Path | str) -> ConvertResult:
    """Convert an Archidekt/CSV/text export into the simple '1 Card' format."""
    if isinstance(source, Path):
        require_file(source, "Input")
    entries = parse_source(source)
    if not entries:
        raise EmptyCollectionError("No cards found in input file", source=_source_label(source))
    aggregated = aggregate_entries(entries)
    return ConvertResult(
        text=convert_to_text(entries),
        unique_cards=len(aggregated),
        total_cards=sum(e.quantity for e in aggregated),
    )
