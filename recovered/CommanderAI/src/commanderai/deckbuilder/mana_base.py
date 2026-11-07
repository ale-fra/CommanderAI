import random
import re
from collections import Counter

from commanderai.deckbuilder.variety import softmax_weights, weighted_sample_without_replacement
from commanderai.models import Card, DeckPick, DeckSlot

_PIP_PATTERN = re.compile(r"\{([WUBRG])\}")

_COLOR_TO_BASIC = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}


def make_basic_land(color: str) -> Card:
    """Construct a basic land Card for a WUBRG color, or None if unmapped."""
    basic_name = _COLOR_TO_BASIC.get(color)
    if not basic_name:
        return None
    return Card(
        name=basic_name,
        type_line="Basic Land",
        color_identity=[],
        oracle_text=f"({{{color}}})",
    )


def count_pips(cards: list[Card]) -> Counter:
    pips: Counter = Counter()
    for card in cards:
        if "Land" in card.type_line:
            continue
        for match in _PIP_PATTERN.finditer(card.mana_cost):
            pips[match.group(1)] += 1
    return pips


def build_mana_base(
    nonland_cards: list[Card],
    collection_lands: list[Card],
    commander: Card,
    land_count: int = 37,
    rng: random.Random | None = None,
    variety: float = 0.0,
    partner: Card | None = None,
) -> list[DeckPick]:
    commanders = [commander] + ([partner] if partner else [])
    pips = count_pips(nonland_cards + commanders)
    identity: set[str] = set()
    for c in commanders:
        identity |= set(c.color_identity)

    # Filter lands to commander's color identity (colorless lands always legal)
    legal_lands = [
        l for l in collection_lands
        if set(l.color_identity).issubset(identity)
    ]

    nonbasic = [l for l in legal_lands if not _is_basic_land(l)]
    nonbasic_target = land_count - 5
    chosen_lands = _choose_nonbasic_lands(nonbasic, identity, nonbasic_target, rng, variety)

    selected: list[DeckPick] = []
    used_names: set[str] = set()
    for land in chosen_lands:
        if land.name in used_names:
            continue
        used_names.add(land.name)
        selected.append(DeckPick(card=land, slot=DeckSlot.LAND, reason="utility/dual land"))

    basics_needed = land_count - len(selected)
    if basics_needed > 0:
        basic_picks = _distribute_basics(pips, identity, basics_needed)
        selected.extend(basic_picks)

    return selected[:land_count]


def _choose_nonbasic_lands(
    nonbasic: list[Card],
    identity: set[str],
    target: int,
    rng: random.Random | None,
    variety: float,
) -> list[Card]:
    """Pick which nonbasic lands to run.

    Deterministic (variety 0) keeps the strict priority order. With variety, the
    lands are sampled weighted by priority so the same fetch/dual package isn't
    grabbed verbatim every build.
    """
    ordered = _sort_lands_by_priority(nonbasic, identity)
    if target <= 0:
        return []
    if variety <= 0 or rng is None or len(ordered) <= target:
        return ordered[:target]
    weights = softmax_weights([_land_priority_score(l, identity) for l in ordered], variety)
    sampled = weighted_sample_without_replacement(rng, ordered, weights, target)
    sampled.sort(key=lambda l: _land_priority_score(l, identity), reverse=True)
    return sampled


def _land_priority_tier(land: Card, identity: set[str]) -> int:
    name_lower = land.name.lower()
    if name_lower == "command tower":
        return 0
    if "fetch" in _land_category(land):
        return 1
    if _produces_multiple_colors(land, identity):
        return 2
    return 3


def _land_priority_score(land: Card, identity: set[str]) -> float:
    tier = _land_priority_tier(land, identity)
    rank = land.edhrec_rank or 99999
    return (3 - tier) * 100 + max(0.0, 100 - rank / 300)


def _sort_lands_by_priority(lands: list[Card], identity: set[str]) -> list[Card]:
    def priority_key(land: Card) -> tuple[int, int]:
        rank = land.edhrec_rank or 99999
        return (_land_priority_tier(land, identity), rank)

    return sorted(lands, key=priority_key)


def _produces_multiple_colors(land: Card, identity: set[str]) -> bool:
    text = (land.oracle_text or "").lower()
    colors_produced = 0
    for color in identity:
        basic_name = _COLOR_TO_BASIC.get(color, "").lower()
        if f"{{{color.lower()}}}" in text or basic_name in text or f"add {{{color}}}" in text.upper():
            colors_produced += 1
    return colors_produced >= 2


def _land_category(land: Card) -> str:
    text = (land.oracle_text or "").lower()
    if "search your library" in text and "land" in text:
        return "fetch"
    return "other"


def _distribute_basics(pips: Counter, identity: set[str], count: int) -> list[DeckPick]:
    total = sum(pips.get(c, 0) for c in identity) or 1
    picks: list[DeckPick] = []

    for color in sorted(identity):
        ratio = pips.get(color, 1) / total
        num = max(1, round(ratio * count))
        basic = make_basic_land(color)
        if not basic:
            continue
        for _ in range(num):
            if len(picks) >= count:
                break
            picks.append(DeckPick(card=basic.model_copy(), slot=DeckSlot.LAND, reason="basic land"))

    while len(picks) < count:
        fallback_color = max(identity, key=lambda c: pips.get(c, 0))
        basic = make_basic_land(fallback_color)
        picks.append(DeckPick(card=basic.model_copy(), slot=DeckSlot.LAND, reason="basic land"))

    return picks[:count]


def _is_basic_land(card: Card) -> bool:
    return "basic" in card.type_line.lower() and "land" in card.type_line.lower()
