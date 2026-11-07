from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class PublicModel(BaseModel):
    """Base for models exposed by the HTTP API.

    Fields with defaults are always present in responses, so the response JSON
    schema marks them required (generated TypeScript types are then exact).
    Affects the JSON schema only, never validation or serialization.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

# Scryfall price fields in order of preference: a card with no regular (nonfoil)
# price is valued at its foil / etched price.
PRICE_KEYS = ("usd", "usd_foil", "usd_etched")


class DeckSlot(str, Enum):
    LAND = "LAND"
    RAMP = "RAMP"
    DRAW = "DRAW"
    REMOVAL = "REMOVAL"
    WIPE = "WIPE"
    THREAT = "THREAT"
    UTILITY = "UTILITY"


class Card(BaseModel):
    name: str
    mana_cost: str = ""
    cmc: float = 0.0
    type_line: str = ""
    oracle_text: str = ""
    color_identity: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    edhrec_rank: int | None = None
    power: str | None = None
    toughness: str | None = None
    legalities: dict[str, str] = Field(default_factory=dict)
    prices: dict[str, str | None] = Field(default_factory=dict)
    set_code: str = ""
    set_name: str = ""
    collector_number: str = ""
    rarity: str = ""
    card_faces: list[dict] | None = None
    game_changer: bool = False

    def price_label(self) -> str | None:
        """The raw USD price string used for this card (see PRICE_KEYS), or None."""
        for key in PRICE_KEYS:
            val = (self.prices or {}).get(key)
            if val:
                try:
                    float(val)
                except (TypeError, ValueError):
                    continue
                return val
        return None

    @property
    def price_usd(self) -> float | None:
        """Best-effort USD price; None when Scryfall has no price for the card."""
        label = self.price_label()
        return float(label) if label is not None else None


class CollectionEntry(BaseModel):
    quantity: int
    card_name: str
    set_code: str | None = None
    collector_number: str | None = None
    card: Card | None = None


class ScoredCard(BaseModel):
    card: Card
    score: float
    slot: DeckSlot
    reasons: list[str] = Field(default_factory=list)


class DeckPick(BaseModel):
    card: Card
    slot: DeckSlot
    reason: str = ""


class Deck(BaseModel):
    commander: Card
    partner: Card | None = None
    cards: list[DeckPick] = Field(default_factory=list)
    strategy_summary: str = ""
    upgrade_suggestions: list[str] = Field(default_factory=list)

    @property
    def commanders(self) -> list[Card]:
        return [self.commander] + ([self.partner] if self.partner else [])

    @property
    def size(self) -> int:
        return len(self.cards) + len(self.commanders)

    @property
    def avg_cmc(self) -> float:
        nonland = [p.card.cmc for p in self.cards if p.slot != DeckSlot.LAND]
        return sum(nonland) / len(nonland) if nonland else 0.0

    @property
    def total_price(self) -> float:
        """Estimated USD price of all 100 cards, commanders included.

        Cards without any price data count as 0 (see ``unpriced_cards``).
        """
        return sum(card.price_usd or 0.0 for card in self._all_cards())

    @property
    def unpriced_cards(self) -> int:
        """Cards (excluding basic lands) with no Scryfall price data."""
        return sum(
            1 for card in self._all_cards()
            if card.price_usd is None and "basic" not in card.type_line.lower()
        )

    def _all_cards(self) -> list[Card]:
        return [p.card for p in self.cards] + self.commanders
