"""API data transfer objects (the JSON contract) and converters from domain objects.

Service-layer models that are already a good public shape (MatchReport,
BudgetReport, BracketReport, AutoPickInfo, Notice, Token, DeckStats, Vocabulary)
are reused as-is so the contract cannot drift from the services.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from commanderai.api.images import CardImages, ImageIndex
from commanderai.deckbuilder.rules import is_legal_commander
from commanderai.deckbuilder.slots import classify_card
from commanderai.models import Card, Deck, DeckSlot, PublicModel
from commanderai.reporting import Notice
from commanderai.services.analysis import DeckStats, Token
from commanderai.services.build import AutoPickInfo, BracketReport, BudgetReport
from commanderai.services.collection import MatchReport
from commanderai.services.commanders import partner_tags
from commanderai.services.reference import Vocabulary

MAX_UPLOAD_CHARS = 2_000_000
ExportFormat = Literal["json", "text", "mtgo", "moxfield", "archidekt"]


# ---------------------------------------------------------------------------
# Errors (documentation only — produced by the exception handlers)
# ---------------------------------------------------------------------------

class ErrorBody(PublicModel):
    code: str
    message: str
    details: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)


class ErrorResponse(PublicModel):
    error: ErrorBody


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

class CardSummary(PublicModel):
    name: str
    mana_cost: str
    cmc: float
    type_line: str
    oracle_text: str
    colors: list[str]
    color_identity: list[str]
    keywords: list[str]
    power: str | None = None
    toughness: str | None = None
    rarity: str = ""
    edhrec_rank: int | None = None
    price_usd: float | None = None
    game_changer: bool = False
    role: DeckSlot
    is_commander: bool
    partner_tags: list[str] = Field(default_factory=list)
    images: CardImages


class CardFace(PublicModel):
    name: str
    mana_cost: str = ""
    type_line: str = ""
    oracle_text: str = ""
    power: str | None = None
    toughness: str | None = None


class CardDetail(CardSummary):
    set_code: str = ""
    set_name: str = ""
    collector_number: str = ""
    prices: dict[str, str | None] = Field(default_factory=dict)
    faces: list[CardFace] = Field(default_factory=list)


def card_summary(card: Card, images: ImageIndex) -> CardSummary:
    return CardSummary(
        name=card.name,
        mana_cost=card.mana_cost,
        cmc=card.cmc,
        type_line=card.type_line,
        oracle_text=card.oracle_text,
        colors=card.colors,
        color_identity=card.color_identity,
        keywords=card.keywords,
        power=card.power,
        toughness=card.toughness,
        rarity=card.rarity,
        edhrec_rank=card.edhrec_rank,
        price_usd=card.price_usd,
        game_changer=card.game_changer,
        role=classify_card(card),
        is_commander=is_legal_commander(card),
        partner_tags=partner_tags(card),
        images=images.images(card.name),
    )


def card_detail(card: Card, images: ImageIndex) -> CardDetail:
    faces = [
        CardFace(
            name=f.get("name", ""), mana_cost=f.get("mana_cost", "") or "",
            type_line=f.get("type_line", "") or "", oracle_text=f.get("oracle_text", "") or "",
            power=f.get("power"), toughness=f.get("toughness"),
        )
        for f in card.card_faces or []
    ]
    return CardDetail(
        **card_summary(card, images).model_dump(),
        set_code=card.set_code, set_name=card.set_name,
        collector_number=card.collector_number, prices=card.prices, faces=faces,
    )


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class CatalogStatus(PublicModel):
    cards: int
    snapshot: str | None = None            # Scryfall bulk export timestamp, if known


class DatabaseStatus(PublicModel):
    decks: int
    collections: int


class MigrationStatus(PublicModel):
    imported: int = 0
    failed: int = 0


class StatusResponse(PublicModel):
    version: str
    offline: bool
    catalog: CatalogStatus
    database: DatabaseStatus
    default_collection: str | None = None  # collection id
    migration: MigrationStatus | None = None


VocabularyResponse = Vocabulary


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

CollectionKind = Literal["builtin", "default", "stored"]


class CollectionInfo(PublicModel):
    id: str
    kind: CollectionKind
    name: str
    description: str = ""
    entries: int                           # parsed lines
    copies: int                            # total quantity
    editable: bool = False


class CollectionDetail(CollectionInfo):
    unique_cards: int
    commanders: int
    match: MatchReport


class CollectionCard(CardSummary):
    quantity: int


class ContentRequest(PublicModel):
    content: str = Field(max_length=MAX_UPLOAD_CHARS, description="Collection text or CSV export")


class CollectionCreate(ContentRequest):
    name: str = Field(min_length=1, max_length=100)


class CollectionUpdate(PublicModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, max_length=MAX_UPLOAD_CHARS)


class CollectionPreview(PublicModel):
    entries: int
    copies: int
    unique_cards: int
    commanders: int
    match: MatchReport


# ---------------------------------------------------------------------------
# Commanders
# ---------------------------------------------------------------------------

class CommanderEntry(PublicModel):
    card: CardSummary
    colors: str                            # WUBRG letters, "C" for colorless
    edhrec_rank: int | None = None
    partner_tags: list[str] = Field(default_factory=list)
    can_take_partner: bool = False
    support: int                           # owned cards within its color identity


class CommanderSuggestionDTO(PublicModel):
    commander: CommanderEntry
    support: int
    edhrec_rank: int
    theme_fit: int = 0
    score: float


class CommanderSuggestions(PublicModel):
    top: int
    theme: str | None = None
    colors: list[str] | None = None
    variety: float = 0.0
    seed: int | None = None
    suggestions: list[CommanderSuggestionDTO]


# ---------------------------------------------------------------------------
# Decks & builds
# ---------------------------------------------------------------------------

class DeckCard(PublicModel):
    card: CardSummary
    slot: DeckSlot
    reason: str = ""


class DeckView(PublicModel):
    commander: CardSummary
    partner: CardSummary | None = None
    cards: list[DeckCard]


def deck_view(deck: Deck, images: ImageIndex) -> DeckView:
    return DeckView(
        commander=card_summary(deck.commander, images),
        partner=card_summary(deck.partner, images) if deck.partner else None,
        cards=[
            DeckCard(card=card_summary(p.card, images), slot=p.slot, reason=p.reason)
            for p in deck.cards
        ],
    )


class BuildParams(PublicModel):
    """The parameters of a build, as the UI sends them (and can send them again)."""

    collection: str = Field(description="Collection id (see GET /api/collections)")
    commander: str | None = None
    partner: str | None = None
    theme: str | None = None
    colors: str | None = None
    lands: int = Field(37, ge=0, le=99)
    variety: float = Field(0.0, ge=0.0, le=1.0)
    seed: int | None = None
    budget: float | None = Field(None, ge=0)
    bracket: int | None = Field(None, ge=1, le=5)


class QuotaChange(PublicModel):
    """How a theme changed a role's target number of cards."""

    before: int
    after: int


class BuildReport(PublicModel):
    """Everything the builder reported, besides the deck itself."""

    theme: str | None = None
    color_filter: list[str] | None = None
    variety: float = 0.0
    seed: int | None = None
    lands: int = 37
    quotas: dict[str, int] = Field(default_factory=dict)
    quota_changes: dict[str, QuotaChange] = Field(default_factory=dict)
    autopick: AutoPickInfo = Field(default_factory=AutoPickInfo)
    match: MatchReport | None = None
    candidate_count: int = 0
    budget: BudgetReport | None = None
    bracket: BracketReport | None = None
    backfilled: int = 0
    shortfall: int = 0
    validation_errors: list[str] = Field(default_factory=list)
    notices: list[Notice] = Field(default_factory=list)

    @field_validator("quota_changes", mode="before")
    @classmethod
    def _pairs_to_objects(cls, value):
        # Builds and stored records carry (before, after) pairs.
        if isinstance(value, dict):
            return {
                k: {"before": v[0], "after": v[1]} if isinstance(v, (list, tuple)) else v
                for k, v in value.items()
            }
        return value


class BuildResultDTO(PublicModel):
    params: BuildParams
    deck: DeckView
    stats: DeckStats
    tokens: list[Token]
    report: BuildReport


class BuildResponse(PublicModel):
    build_id: str
    expires_at: str                        # ISO-8601 UTC
    result: BuildResultDTO


class SaveBuildRequest(PublicModel):
    build_id: str
    name: str | None = Field(default=None, max_length=200)


class DeckSummaryDTO(PublicModel):
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
    created_at: str
    updated_at: str
    commander_image: str | None = None


class DeckList(PublicModel):
    total: int
    items: list[DeckSummaryDTO]


class DeckDetail(PublicModel):
    id: int
    name: str
    source: str
    created_at: str
    updated_at: str
    notes: str = ""
    collection_source: str | None = None
    export_path: str | None = None
    export_format: str | None = None
    deck: DeckView
    stats: DeckStats
    tokens: list[Token]
    validation_errors: list[str]
    report: BuildReport | None = None      # None for imported / legacy decks
    params: BuildParams | None = None      # set when the build can be repeated from the UI


class DeckUpdate(PublicModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=10_000)


class DeckImportRequest(ContentRequest):
    name: str | None = Field(default=None, max_length=200)
    filename: str | None = Field(default=None, max_length=255)


class DeckImportResponse(PublicModel):
    deck: DeckDetail
    unknown_cards: list[str]
