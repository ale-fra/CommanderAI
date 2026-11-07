from typing import Annotated

from fastapi import APIRouter, Query

from commanderai.api.registry import ref_label, ref_source, resolve_ref
from commanderai.api.routers import ERROR_RESPONSES
from commanderai.api.routers.collections import load_ref
from commanderai.api.schemas import (
    CardSummary,
    CommanderEntry,
    CommanderSuggestionDTO,
    CommanderSuggestions,
    card_summary,
)
from commanderai.api.state import ApiState, State
from commanderai.deckbuilder.partner import can_partner
from commanderai.errors import CardNotFoundError
from commanderai.models import Card
from commanderai.services.commanders import CommanderInfo, list_commanders, suggest_commanders

router = APIRouter(prefix="/api/commanders", tags=["commanders"], responses=ERROR_RESPONSES)


def _support(commander: Card, owned: list[Card]) -> int:
    identity = set(commander.color_identity)
    return sum(1 for c in owned if c.name != commander.name and set(c.color_identity) <= identity)


def _entry(info: CommanderInfo, owned: list[Card], state: ApiState) -> CommanderEntry:
    return CommanderEntry(
        card=card_summary(info.card, state.images),
        colors=info.colors,
        edhrec_rank=info.edhrec_rank,
        partner_tags=info.partner_tags,
        can_take_partner=info.can_take_partner,
        support=_support(info.card, owned),
    )


@router.get("", response_model=list[CommanderEntry])
def commanders(
    state: State,
    collection: str,
    colors: str | None = None,
) -> list[CommanderEntry]:
    """Every legal commander in the collection (sorted by EDHREC rank)."""
    ctx = state.ctx()
    ref = resolve_ref(ctx, collection, state.sample_dir)
    source = ref_source(ctx, ref)
    infos = list_commanders(ctx, source, colors)
    _, loaded = load_ref(state, ctx, collection)
    return [_entry(info, loaded.cards, state) for info in infos]


@router.get("/suggestions", response_model=CommanderSuggestions)
def suggestions(
    state: State,
    collection: str,
    theme: str | None = None,
    colors: str | None = None,
    top: Annotated[int,
    Query(ge=1, le=50)] = 5,
    variety: Annotated[float,
    Query(ge=0.0, le=1.0)] = 0.0,
    seed: int | None = None,
) -> CommanderSuggestions:
    """Owned commanders ranked by supporting cards, theme fit and EDHREC rank."""
    ctx = state.ctx()
    ref = resolve_ref(ctx, collection, state.sample_dir)
    result = suggest_commanders(
        ctx, ref_source(ctx, ref), colors=colors, theme=theme, top=top, variety=variety, seed=seed
    )
    _, loaded = load_ref(state, ctx, collection)
    return CommanderSuggestions(
        top=result.top, theme=result.theme, colors=result.colors,
        variety=result.variety, seed=result.seed,
        suggestions=[
            CommanderSuggestionDTO(
                commander=_entry(s.commander, loaded.cards, state),
                support=s.support, edhrec_rank=s.edhrec_rank, theme_fit=s.theme_fit, score=s.score,
            )
            for s in result.suggestions
        ],
    )


@router.get("/partners", response_model=list[CardSummary])
def partners(state: State, collection: str, commander: str) -> list[CardSummary]:
    """Owned cards that can legally share the command zone with ``commander``."""
    ctx = state.ctx()
    found = ctx.catalog().get(commander)
    if not found:
        raise CardNotFoundError(f"Commander '{commander}' not found", name=commander)
    _, loaded = load_ref(state, ctx, collection)
    return [card_summary(c, state.images) for c in loaded.cards if can_partner(found, c)]


__all__ = ["ref_label", "router"]
