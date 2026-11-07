import random
import re

import anthropic

from commanderai.config import ANTHROPIC_API_KEY, LLM_MODEL
from commanderai.models import Card, DeckSlot
from commanderai.deckbuilder.rules import color_identity_filter
from commanderai.deckbuilder.slots import classify_card
from commanderai.deckbuilder.themes import theme_hits
from commanderai.deckbuilder.variety import softmax_weights, weighted_sample_without_replacement

_THEME_BONUS_PER_HIT = 20.0
_THEME_BONUS_CAP = 60.0
# When sampling for variety, draw from this many times top_n of the best matches
# so picks stay strong but aren't always the identical top-N.
_VARIETY_POOL_MULTIPLIER = 4


def _extract_themes(commander: Card) -> list[str]:
    """Extract mechanical themes from commander text for keyword matching."""
    text = (commander.oracle_text or "").lower()
    type_line = commander.type_line.lower()
    themes = []

    if "transform" in text or "//" in commander.name:
        themes.append("transform")
    if "counter" in text or "+1/+1" in text or "proliferate" in text:
        themes.append("counters")
    if "token" in text or "create" in text:
        themes.append("tokens")
    if "draw" in text:
        themes.append("draw")
    if "graveyard" in text or "dies" in text:
        themes.append("graveyard")
    if "combat" in text or "attack" in text:
        themes.append("combat")
    if "life" in text or "lifelink" in text.lower():
        themes.append("lifegain")
    if "sacrifice" in text:
        themes.append("sacrifice")
    if "spell" in text or "cast" in text:
        themes.append("spellslinger")
    if "human" in type_line or "human" in text:
        themes.append("human")
    if "flying" in text:
        themes.append("flying")

    return themes


_THEME_PATTERNS = {
    "transform": [
        r"transform",
        r"night\b",
        r"daybound",
        r"nightbound",
        r"flip",
    ],
    "counters": [
        r"\+1/\+1 counter",
        r"proliferate",
        r"counter on",
        r"modular",
        r"evolve",
    ],
    "tokens": [
        r"create.*token",
        r"populate",
        r"doubling",
    ],
    "draw": [
        r"draw.*card",
        r"whenever.*draw",
    ],
    "graveyard": [
        r"graveyard",
        r"return.*from.*graveyard",
        r"unearth",
        r"flashback",
        r"dredge",
    ],
    "combat": [
        r"extra combat",
        r"additional combat",
        r"whenever.*attacks",
        r"double strike",
    ],
    "lifegain": [
        r"gain.*life",
        r"lifelink",
        r"whenever you gain life",
    ],
    "sacrifice": [
        r"sacrifice",
        r"when.*dies",
        r"death trigger",
    ],
    "spellslinger": [
        r"whenever you cast",
        r"instant or sorcery",
        r"magecraft",
        r"prowess",
        r"copy.*spell",
    ],
    "human": [
        r"human",
        r"all humans",
        r"each human",
    ],
    "flying": [
        r"flying",
        r"creatures with flying",
    ],
}


def _direct_synergy_bonus(card: Card, commander: Card, card_full_text: str) -> float:
    """Bonus for cards that directly reference/enable the commander's mechanics."""
    bonus = 0.0
    cmdr_text = (commander.oracle_text or "").lower()
    cmdr_type = commander.type_line.lower()

    # Card references the commander's creature types
    cmdr_types = _extract_creature_types(cmdr_type)
    for ct in cmdr_types:
        if ct in card_full_text:
            bonus += 25

    # Card says "transform" and commander is double-faced
    if "//" in commander.name and "transform" in card_full_text:
        bonus += 30
        # Extra bonus for spells that actively transform (enablers, not just DFCs themselves)
        card_type = card.type_line.lower()
        if "//" not in card.name and ("instant" in card_type or "sorcery" in card_type or "enchantment" in card_type):
            bonus += 40

    # Card references a keyword the commander has
    cmdr_keywords = {k.lower() for k in commander.keywords}
    card_text = (card.oracle_text or "").lower()
    for kw in cmdr_keywords:
        if kw in card_text and kw not in ("flying",):
            bonus += 15

    return bonus


def _extract_creature_types(type_line: str) -> list[str]:
    """Extract creature subtypes from type line."""
    if "—" not in type_line:
        return []
    subtypes_part = type_line.split("—")[1].strip()
    # Filter out generic types that match too broadly
    generic = {"creature", "legendary", "artifact", "enchantment"}
    types = [t.strip().lower() for t in subtypes_part.split()]
    return [t for t in types if t and t not in generic and len(t) > 3]


def find_suggestions_heuristic(
    commander: Card,
    all_cards: list[Card],
    owned_names: set[str],
    top_n: int = 20,
    rng: random.Random | None = None,
    variety: float = 0.0,
    theme: str | None = None,
) -> list[tuple[Card, list[str]]]:
    """Find high-synergy cards NOT in collection using theme matching.

    ``variety``/``rng`` and ``theme`` are opt-in: with the defaults the result
    is the deterministic top-N exactly as before.
    """
    themes = _extract_themes(commander)
    if not themes and not theme:
        return []

    legal_pool = color_identity_filter(all_cards, commander)
    not_owned = [c for c in legal_pool if c.name not in owned_names and c.name != commander.name]

    scored: list[tuple[Card, float, list[str]]] = []

    for card in not_owned:
        if classify_card(card) == DeckSlot.LAND:
            continue

        text = (card.oracle_text or "").lower()
        type_line = card.type_line.lower()
        full_text = text + " " + type_line

        hits: list[str] = []
        for t in themes:
            patterns = _THEME_PATTERNS.get(t, [])
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    hits.append(t)
                    break

        theme_bonus = 0.0
        if theme:
            th = theme_hits(theme, card.oracle_text, card.type_line)
            if th > 0:
                theme_bonus = min(th * _THEME_BONUS_PER_HIT, _THEME_BONUS_CAP)
                if theme not in hits:
                    hits.append(theme)

        if not hits:
            continue

        score = len(hits) * 30
        if card.edhrec_rank:
            score += max(0, 100 - (card.edhrec_rank / 300))
        if card.cmc <= 3:
            score += 5
        score += theme_bonus

        # Bonus for cards that directly enable commander's core mechanic
        score += _direct_synergy_bonus(card, commander, full_text)

        scored.append((card, score, hits))

    scored.sort(key=lambda x: x[1], reverse=True)

    if variety > 0 and rng is not None and len(scored) > top_n:
        pool = scored[: max(top_n * _VARIETY_POOL_MULTIPLIER, top_n)]
        weights = softmax_weights([s for _, s, _ in pool], variety)
        sampled = weighted_sample_without_replacement(rng, pool, weights, top_n)
        sampled.sort(key=lambda x: x[1], reverse=True)
        return [(card, hits) for card, _, hits in sampled]

    return [(card, hits) for card, _, hits in scored[:top_n]]


def find_suggestions_llm(
    commander: Card,
    deck_cards: list[Card],
    owned_names: set[str],
    all_cards: list[Card],
    top_n: int = 15,
    rng: random.Random | None = None,
    variety: float = 0.0,
    theme: str | None = None,
) -> str:
    """Use LLM to suggest upgrades with reasoning."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")

    themes = _extract_themes(commander)

    # Get top heuristic suggestions to give LLM context on what's available
    heuristic_picks = find_suggestions_heuristic(
        commander, all_cards, owned_names, top_n=40,
        rng=rng, variety=variety, theme=theme,
    )
    if variety > 0 and rng is not None:
        heuristic_picks = heuristic_picks[:]
        rng.shuffle(heuristic_picks)

    lines = []
    lines.append("## Commander")
    lines.append(f"**{commander.name}** — {commander.type_line}")
    lines.append(f"Cost: {commander.mana_cost}")
    lines.append(f"Text: {commander.oracle_text}")
    lines.append(f"Detected themes: {', '.join(themes)}")
    lines.append("")
    lines.append(f"## Current Deck ({len(deck_cards)} cards)")
    for card in sorted(deck_cards, key=lambda c: c.cmc)[:50]:
        lines.append(f"- {card.name} {card.mana_cost}")
    if len(deck_cards) > 50:
        lines.append(f"... and {len(deck_cards) - 50} more")
    lines.append("")
    lines.append("## Cards NOT owned that have synergy potential:")
    for card, hits in heuristic_picks:
        price = card.price_label() or "?"
        lines.append(
            f"- {card.name} {card.mana_cost} (${price}, EDHREC #{card.edhrec_rank or '?'}) "
            f"— {card.oracle_text[:100]}"
        )
    lines.append("")
    lines.append(f"## Task")
    lines.append(f"Pick the {top_n} best upgrade cards from the list above (or suggest others).")
    lines.append("For each card explain in 1 sentence WHY it's great with this commander.")
    lines.append("Sort by impact — most impactful first.")
    lines.append("Include approximate price if known.")
    if theme:
        lines.append(f"Lean the suggestions toward a '{theme}' strategy.")
    if variety > 0:
        lines.append(
            "Offer a fresh, varied mix — don't just list the most obvious staples; "
            "include some less common but genuinely synergistic options."
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=3000,
        system=(
            "You are an expert MTG Commander deck advisor. "
            "Suggest upgrade cards the player should buy to improve their deck. "
            "Focus on cards with obvious, powerful synergy with the commander's mechanics. "
            "Be specific about WHY each card is good here."
        ),
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )

    return message.content[0].text
