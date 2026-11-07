"""Persistence models.

A :class:`DeckRecord` is the unit stored in the ``decks`` table (as JSON in the
``record`` column, with a few denormalised columns for listing/filtering). It
holds a *full snapshot* of the built ``Deck`` (cards with oracle text, prices,
…), so a saved deck never changes when the card catalog is refreshed.

The same document (minus database identity) is the JSON import/export format.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from commanderai.deckbuilder.colors import format_colors
from commanderai.deckbuilder.partner import combined_identity
from commanderai.models import Deck

RECORD_SCHEMA_VERSION = 1
DECK_EXPORT_FORMAT = "commanderai.deck"

SOURCES = ("cli", "api", "import", "legacy")


class DeckRecord(BaseModel):
    schema_version: int = RECORD_SCHEMA_VERSION
    id: int | None = None
    name: str
    source: str = "api"                      # cli | api | import | legacy
    created_at: str | None = None            # ISO-8601 UTC, set by the repository
    updated_at: str | None = None
    deck: Deck
    build: dict[str, Any] | None = None      # build parameters/report (None for imports)
    collection_source: str | None = None     # collection file / "<text>" / "collection:#id"
    export_path: str | None = None           # text file written alongside (CLI)
    export_format: str | None = None
    notes: str = ""

    @property
    def commander_label(self) -> str:
        return " + ".join(c.name for c in self.deck.commanders)

    @property
    def colors(self) -> str:
        return format_colors(combined_identity(self.deck.commander, self.deck.partner))

    def _build(self, key: str) -> Any:
        return (self.build or {}).get(key)

    def columns(self) -> dict[str, Any]:
        """Denormalised values for the ``decks`` table columns."""
        request = self._build("request") or {}
        return {
            "name": self.name,
            "commander": self.deck.commander.name,
            "partner": self.deck.partner.name if self.deck.partner else None,
            "colors": self.colors,
            "theme": self._build("theme"),
            "seed": self._build("seed"),
            "variety": self._build("variety") or 0.0,
            "bracket": request.get("bracket"),
            "budget": request.get("budget"),
            "card_count": self.deck.size,
            "total_price": round(self.deck.total_price, 2),
            "avg_cmc": round(self.deck.avg_cmc, 4),
            "source": self.source,
            "collection_source": self.collection_source,
            "export_path": self.export_path,
            "export_format": self.export_format,
        }


class DeckSummary(BaseModel):
    """A row of the deck library (no card list)."""

    id: int
    name: str
    commander: str
    partner: str | None = None
    colors: str
    theme: str | None = None
    seed: int | None = None
    variety: float = 0.0
    bracket: int | None = None
    budget: float | None = None
    card_count: int
    total_price: float
    avg_cmc: float
    source: str
    collection_source: str | None = None
    export_path: str | None = None
    export_format: str | None = None
    created_at: str
    updated_at: str

    @property
    def commander_label(self) -> str:
        return f"{self.commander} + {self.partner}" if self.partner else self.commander


class StoredCollection(BaseModel):
    id: int
    name: str
    entries: int                       # parsed lines
    copies: int                        # sum of quantities
    created_at: str
    updated_at: str
    content: str | None = Field(default=None, repr=False)  # omitted in listings


class LegacyImportRow(BaseModel):
    path: str
    sha256: str
    deck_id: int | None = None
    status: str                        # imported | skipped | failed
    message: str | None = None
    imported_at: str
