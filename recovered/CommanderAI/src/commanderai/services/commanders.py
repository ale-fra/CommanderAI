"""Commander discovery: eligible commanders, ranked suggestions, auto-pick."""

from __future__ import annotations

import random
from pathlib import Path

from pydantic import BaseModel, Field

from commanderai.deckbuilder.colors import format_colors
from commanderai.deckbuilder.partner import can_partner, partner_ability
from commanderai.deckbuilder.rules import is_legal_commander
from commanderai.deckbuilder.themes import theme_hits
from commanderai.deckbuilder.variety import softmax_weights, weighted_sample_without_replacement
from commanderai.models import Card
from commanderai.services.collection import load_collection
from commanderai.services.common import (
    resolve_colors_or_raise,
    resolve_theme_or_raise,
    setup_variety,
)
from commanderai.services.context import ServiceContext

# ---------------------------------------------------------------------------
# Auto-pick (used by build when no --commander is given)
# ---------------------------------------------------------------------------

def auto_select_commander(
    collection_cards: list,
    theme: str | None,
    color_filter: set[str] | None,
    rng: random.Random | None,
    variety: float,
) -> tuple | None:
    """Pick the best-fit owned commander for a theme/colors when none is given.

    Scores each legal commander you own by on-theme card support in its colors,
    its own theme fit, and EDHREC rank. Returns (commander, on_theme_support,
    theme_fit) or None if no eligible commander exists.
    """
    legal = [c for c in collection_cards if is_legal_commander(c)]
    if color_filter is not None:
        legal = [c for c in legal if set(c.color_identity).issubset(color_filter)]
    if not legal:
        return None

    # Precompute which owned cards are on-theme (for support counting).
    if theme:
        on_theme = [
            c for c in collection_cards
            if theme_hits(theme, c.oracle_text, c.type_line) > 0
        ]
    else:
        on_theme = collection_cards

    scored: list[tuple] = []
    for cmdr in legal:
        identity = set(cmdr.color_identity)
        support = sum(
            1 for c in on_theme
            if c.name != cmdr.name and set(c.color_identity).issubset(identity)
        )
        fit = theme_hits(theme, cmdr.oracle_text, cmdr.type_line) if theme else 0
        rank_bonus = max(0.0, 100 - (cmdr.edhrec_rank or 99999) / 300)
        weight = fit * 60 + support + rank_bonus
        scored.append((cmdr, support, fit, weight))

    scored.sort(key=lambda x: x[3], reverse=True)

    if variety > 0 and rng is not None and len(scored) > 1:
        pool = scored[: max(8, 1)]
        weights = softmax_weights([x[3] for x in pool], variety)
        chosen = weighted_sample_without_replacement(rng, pool, weights, 1)[0]
    else:
        chosen = scored[0]
    return chosen[0], chosen[1], chosen[2]


def auto_select_partner(
    commander,
    collection_cards: list,
    theme: str | None,
    color_filter: set[str] | None,
    rng: random.Random | None,
    variety: float,
):
    """Find the best owned partner for a commander that wants one, or None."""
    if not partner_ability(commander).can_take_partner:
        return None

    primary_colors = set(commander.color_identity)
    eligible = []
    for c in collection_cards:
        if c.name == commander.name or not can_partner(commander, c):
            continue
        union = primary_colors | set(c.color_identity)
        if color_filter is not None and not union.issubset(color_filter):
            continue
        eligible.append(c)
    if not eligible:
        return None

    scored = []
    for c in eligible:
        fit = theme_hits(theme, c.oracle_text, c.type_line) if theme else 0
        new_colors = len(set(c.color_identity) - primary_colors)
        rank_bonus = max(0.0, 100 - (c.edhrec_rank or 99999) / 300)
        weight = fit * 50 + new_colors * 15 + rank_bonus
        scored.append((c, weight))
    scored.sort(key=lambda x: x[1], reverse=True)

    if variety > 0 and rng is not None and len(scored) > 1:
        pool = scored[:8]
        weights = softmax_weights([w for _, w in pool], variety)
        return weighted_sample_without_replacement(rng, pool, weights, 1)[0][0]
    return scored[0][0]


# ---------------------------------------------------------------------------
# Listing eligible commanders
# ---------------------------------------------------------------------------

def partner_tags(card: Card) -> list[str]:
    """Human-readable partner-ability tags (e.g. 'Partner', 'Choose a Background')."""
    ability = partner_ability(card)
    tags = []
    if ability.partner_with:
        tags.append(f"Partner with {ability.partner_with[0]}")
    elif ability.plain:
        tags.append("Partner")
    if ability.group:
        tags.append(f"Partner — {ability.group}")
    if ability.background_chooser:
        tags.append("Choose a Background")
    if ability.doctors_companion:
        tags.append("Doctor's companion")
    if ability.friends_forever:
        tags.append("Friends forever")
    return tags


class CommanderInfo(BaseModel):
    card: Card
    colors: str                       # WUBRG-ordered letters ("C" if colorless)
    edhrec_rank: int | None = None
    partner_tags: list[str] = Field(default_factory=list)
    can_take_partner: bool = False

    @property
    def name(self) -> str:
        return self.card.name


def commander_info(card: Card) -> CommanderInfo:
    return CommanderInfo(
        card=card,
        colors=format_colors(card.color_identity),
        edhrec_rank=card.edhrec_rank,
        partner_tags=partner_tags(card),
        can_take_partner=partner_ability(card).can_take_partner,
    )


def list_commanders(
    ctx: ServiceContext, collection: Path | str, colors: str | None = None
) -> list[CommanderInfo]:
    """Every legal commander in the collection, sorted by EDHREC rank then name."""
    color_filter = resolve_colors_or_raise(colors)
    loaded = load_collection(ctx, collection)
    commanders = [c for c in loaded.cards if is_legal_commander(c)]
    if color_filter is not None:
        commanders = [c for c in commanders if set(c.color_identity).issubset(color_filter)]
    commanders.sort(key=lambda c: (c.edhrec_rank or 99999, c.name))
    return [commander_info(c) for c in commanders]


# ---------------------------------------------------------------------------
# Ranked suggestions
# ---------------------------------------------------------------------------

class CommanderSuggestion(BaseModel):
    commander: CommanderInfo
    support: int          # owned cards in its colors (on-theme only, when a theme is set)
    edhrec_rank: int      # 99999 when unknown
    theme_fit: int = 0
    score: float


class SuggestCommandersResult(BaseModel):
    top: int
    theme: str | None = None
    colors: list[str] | None = None
    variety: float = 0.0
    seed: int | None = None
    suggestions: list[CommanderSuggestion]


def suggest_commanders(
    ctx: ServiceContext,
    collection: Path | str,
    *,
    colors: str | None = None,
    theme: str | None = None,
    top: int = 5,
    variety: float = 0.0,
    seed: int | None = None,
) -> SuggestCommandersResult:
    """Rank owned commanders by supporting cards (and theme fit / EDHREC rank)."""
    theme = resolve_theme_or_raise(theme)
    color_filter = resolve_colors_or_raise(colors)
    var = setup_variety(variety, seed, ctx.reporter)
    loaded = load_collection(ctx, collection)
    collection_cards = loaded.cards

    owned_commanders = [c for c in collection_cards if is_legal_commander(c)]
    if color_filter is not None:
        owned_commanders = [
            c for c in owned_commanders
            if set(c.color_identity).issubset(color_filter)
        ]

    on_theme = (
        {c.name for c in collection_cards if theme_hits(theme, c.oracle_text, c.type_line) > 0}
        if theme else None
    )

    scored: list[tuple[Card, int, int, int, float]] = []
    for cmdr in owned_commanders:
        identity = set(cmdr.color_identity)
        support = sum(
            1 for c in collection_cards
            if c.name != cmdr.name
            and set(c.color_identity).issubset(identity)
            and (on_theme is None or c.name in on_theme)
        )
        rank = cmdr.edhrec_rank or 99999
        fit = theme_hits(theme, cmdr.oracle_text, cmdr.type_line) if theme else 0
        weight_score = fit * 60 + support + max(0.0, 100 - rank / 300)
        scored.append((cmdr, support, rank, fit, weight_score))

    scored.sort(key=lambda x: (-x[4], x[2]))

    if var.variety > 0 and var.rng is not None and len(scored) > top:
        pool = scored[: max(top * 4, top)]
        weights = softmax_weights([x[4] for x in pool], var.variety)
        chosen = weighted_sample_without_replacement(var.rng, pool, weights, top)
        chosen.sort(key=lambda x: (-x[1], x[2]))
    else:
        chosen = scored[:top]

    return SuggestCommandersResult(
        top=top,
        theme=theme,
        colors=sorted(color_filter) if color_filter is not None else None,
        variety=var.variety,
        seed=var.seed,
        suggestions=[
            CommanderSuggestion(
                commander=commander_info(cmdr), support=support, edhrec_rank=rank,
                theme_fit=fit, score=weight,
            )
            for cmdr, support, rank, fit, weight in chosen
        ],
    )
