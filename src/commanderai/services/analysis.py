"""Deck analysis use-cases: validation, token listing, AI explanation."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from commanderai.config import SLOT_QUOTAS
from commanderai.deckbuilder.partner import can_partner, partner_ability
from commanderai.deckbuilder.rules import is_legal_commander, validate_deck
from commanderai.deckbuilder.slots import classify_card
from commanderai.deckbuilder.tokens import TokenInfo, extract_tokens
from commanderai.errors import CardNotFoundError, CommanderNotIdentifiedError, LLMError
from commanderai.models import Card, Deck, DeckPick, DeckSlot, PublicModel
from commanderai.services.collection import MatchReport, load_collection
from commanderai.services.context import ServiceContext

# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    commander: str
    partner: str | None = None
    card_count: int                 # commanders + every copy of every recognised card
    errors: list[str] = Field(default_factory=list)
    unknown_cards: list[str] = Field(default_factory=list)   # lines not found in the catalog
    match: MatchReport

    @property
    def valid(self) -> bool:
        return not self.errors


def validate_deck_list(
    ctx: ServiceContext,
    source: Path | str,
    commander_name: str,
    partner_name: str | None = None,
) -> ValidationResult:
    """Check a decklist (file or text) against Commander deck-construction rules.

    Quantities count ("15 Plains" is 15 cards). The commander (and partner) may
    appear in the list or not; they are always counted once. Checks: deck size,
    color identity, singleton (basics exempt), commander legality, partner pairing.
    """
    loaded = load_collection(ctx, source, kind="Deck")
    index = ctx.catalog()

    commander = index.get(commander_name)
    if not commander:
        raise CardNotFoundError(f"Commander '{commander_name}' not found", name=commander_name)
    partner = None
    if partner_name:
        partner = index.get(partner_name)
        if not partner:
            raise CardNotFoundError(f"Partner '{partner_name}' not found", name=partner_name)

    command_zone = {commander.name} | ({partner.name} if partner else set())
    picks = [
        DeckPick(card=e.card, slot=classify_card(e.card))
        for e in loaded.match.matched
        if e.card and e.card.name not in command_zone
        for _ in range(max(e.quantity, 1))
    ]

    errors: list[str] = []
    if not is_legal_commander(commander):
        errors.append(f"{commander.name} can't be a commander")
    if partner and not is_legal_commander(partner) and not partner_ability(partner).is_background:
        errors.append(f"{partner.name} can't be a commander")
    if partner and not can_partner(commander, partner):
        errors.append(f"{commander.name} and {partner.name} can't be partners")
    errors += validate_deck(commander, picks, partner=partner)

    return ValidationResult(
        commander=commander.name,
        partner=partner.name if partner else None,
        card_count=len(picks) + len(command_zone),
        errors=errors,
        unknown_cards=list(loaded.match.unmatched),
        match=loaded.report,
    )


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

class Token(PublicModel):
    name: str
    power: str | None = None
    toughness: str | None = None
    colors: list[str] = Field(default_factory=list)
    types: str = ""
    keywords: list[str] = Field(default_factory=list)
    created_by: list[str] = Field(default_factory=list)

    @classmethod
    def from_info(cls, t: TokenInfo) -> Token:
        return cls(
            name=t.name, power=t.power, toughness=t.toughness, colors=list(t.colors),
            types=t.types, keywords=list(t.keywords), created_by=list(t.created_by),
        )


class TokensResult(BaseModel):
    tokens: list[Token]
    card_count: int                 # matched cards analysed


def tokens_for_cards(cards: list[Card]) -> list[Token]:
    return [Token.from_info(t) for t in extract_tokens(cards)]


def deck_tokens(ctx: ServiceContext, source: Path | str) -> TokensResult:
    """All tokens the cards of a decklist (file or text) can create."""
    loaded = load_collection(ctx, source, kind="Deck", empty_message="No cards found in deck file")
    matched_cards = [e.card for e in loaded.match.matched if e.card]
    return TokensResult(tokens=tokens_for_cards(matched_cards), card_count=len(matched_cards))


# ---------------------------------------------------------------------------
# explain (LLM)
# ---------------------------------------------------------------------------

class ExplainResult(BaseModel):
    commander: str
    card_count: int
    explanation: str


def explain_deck_list(
    ctx: ServiceContext, source: Path | str, commander_name: str | None = None
) -> ExplainResult:
    """AI explanation of a decklist's strategy. Requires an Anthropic API key."""
    from commanderai.deckbuilder.explainer import explain_deck

    loaded = load_collection(ctx, source, kind="Deck", empty_message="No cards found in deck file")
    index = ctx.catalog()
    matched_cards = [e.card for e in loaded.match.matched if e.card]

    commander = None
    if commander_name:
        commander = index.get(commander_name)
    else:
        for entry in loaded.match.matched:
            if entry.card and is_legal_commander(entry.card):
                commander = entry.card
                break
    if not commander:
        raise CommanderNotIdentifiedError("Could not identify commander. Use --commander flag.")

    deck_cards = [c for c in matched_cards if c.name != commander.name]
    ctx.reporter.info(
        "explain.started",
        f"Explaining: {commander.name} ({len(deck_cards)} cards)",
        commander=commander.name, card_count=len(deck_cards),
    )
    with ctx.reporter.progress("Analyzing deck with Claude..."):
        try:
            if ctx.settings.offline and ctx.settings.has_llm_key:
                raise RuntimeError("offline mode (COMMANDERAI_OFFLINE=1)")
            explanation = explain_deck(commander, deck_cards)
        except Exception as e:
            raise LLMError(str(e)) from e
    return ExplainResult(commander=commander.name, card_count=len(deck_cards), explanation=explanation)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

_TYPE_PRECEDENCE = (
    "Creature", "Land", "Planeswalker", "Battle", "Instant", "Sorcery", "Artifact", "Enchantment",
)
_PIP_RE = re.compile(r"\{([^}]+)\}")
CURVE_BUCKETS = ("0", "1", "2", "3", "4", "5", "6", "7+")


def primary_type(type_line: str) -> str:
    """The card type used for grouping ('Artifact Creature' → Creature)."""
    front = type_line.split("//")[0].split("—")[0]
    for t in _TYPE_PRECEDENCE:
        if t in front:
            return t
    return "Other"


class DeckStats(PublicModel):
    card_count: int
    total_price: float
    unpriced_cards: int
    avg_cmc: float
    lands: int
    mana_curve: dict[str, int]              # nonland cards of the 99 by mana value, "7+" = 7 or more
    color_pips: dict[str, int]              # colored mana symbols in nonland costs (hybrid counts each color)
    roles: dict[str, int]                   # cards per role (slot)
    role_targets: dict[str, int]            # target per role (build quotas; defaults otherwise)
    types: dict[str, int]                   # cards per primary type (commanders included)


def deck_stats(deck: Deck, role_targets: dict[str, int] | None = None) -> DeckStats:
    nonland = [p for p in deck.cards if p.slot != DeckSlot.LAND]
    curve = dict.fromkeys(CURVE_BUCKETS, 0)
    pips = dict.fromkeys("WUBRG", 0)
    for pick in nonland:
        cmc = int(pick.card.cmc)
        curve["7+" if cmc >= 7 else str(cmc)] += 1
        for symbol in _PIP_RE.findall(pick.card.mana_cost):
            for color in set(symbol.upper()) & set("WUBRG"):
                pips[color] += 1

    roles = {slot.value: 0 for slot in DeckSlot}
    for pick in deck.cards:
        roles[pick.slot.value] += 1

    lands = roles["LAND"]
    targets = dict(role_targets or SLOT_QUOTAS)
    targets["LAND"] = targets.get("LAND", lands) if role_targets else lands

    types: dict[str, int] = {}
    for card in [p.card for p in deck.cards] + deck.commanders:
        t = primary_type(card.type_line)
        types[t] = types.get(t, 0) + 1

    return DeckStats(
        card_count=deck.size,
        total_price=round(deck.total_price, 2),
        unpriced_cards=deck.unpriced_cards,
        avg_cmc=round(deck.avg_cmc, 2),
        lands=lands,
        mana_curve=curve,
        color_pips=pips,
        roles=roles,
        role_targets=targets,
        types=dict(sorted(types.items(), key=lambda kv: (-kv[1], kv[0]))),
    )


def deck_validation_errors(deck: Deck) -> list[str]:
    """Deck-construction problems of a stored/built deck (empty = legal)."""
    return validate_deck(deck.commander, deck.cards, partner=deck.partner)
