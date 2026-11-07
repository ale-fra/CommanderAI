"""Upgrade suggestions: cards you don't own that synergize with a commander."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from commanderai.errors import CardNotFoundError, LLMError
from commanderai.models import Card
from commanderai.services.collection import load_collection, resolve_collection_source
from commanderai.services.common import resolve_theme_or_raise, setup_variety
from commanderai.services.context import ServiceContext


class UpgradeSuggestion(BaseModel):
    card: Card
    synergies: list[str] = Field(default_factory=list)


class UpgradeRequest(BaseModel):
    collection: Path | None = None
    collection_text: str | None = None
    collection_id: int | None = None
    commander: str
    deck: Path | None = None          # current deck (only used by the LLM mode)
    top: int = 15
    use_llm: bool = False
    variety: float = Field(0.0, ge=0.0, le=1.0)
    seed: int | None = None
    theme: str | None = None


class UpgradeResult(BaseModel):
    commander: str
    owned_unique: int
    theme: str | None = None
    variety: float = 0.0
    seed: int | None = None
    suggestions: list[UpgradeSuggestion] = Field(default_factory=list)  # heuristic mode
    llm_text: str | None = None                                         # LLM mode


def suggest_upgrades(ctx: ServiceContext, req: UpgradeRequest) -> UpgradeResult:
    from commanderai.deckbuilder.suggester import (
        find_suggestions_heuristic,
        find_suggestions_llm,
    )

    theme = resolve_theme_or_raise(req.theme)
    var = setup_variety(req.variety, req.seed, ctx.reporter)
    source, label = resolve_collection_source(
        ctx, req.collection, req.collection_text, req.collection_id
    )
    loaded = load_collection(ctx, source, label=label)
    index = ctx.catalog()
    owned_names = {e.card.name for e in loaded.match.matched if e.card}

    commander = index.get(req.commander)
    if not commander:
        raise CardNotFoundError(f"Commander '{req.commander}' not found", name=req.commander)

    deck_cards: list[Card] = []
    if req.deck:
        deck = load_collection(ctx, req.deck, kind="Deck")
        deck_cards = [e.card for e in deck.match.matched if e.card and e.card.name != commander.name]

    ctx.reporter.info(
        "suggest.started",
        f"Suggesting upgrades for: {commander.name}",
        commander=commander.name, owned_unique=len(owned_names),
    )
    result = UpgradeResult(
        commander=commander.name, owned_unique=len(owned_names),
        theme=theme, variety=var.variety, seed=var.seed,
    )

    if not req.use_llm:
        suggestions = find_suggestions_heuristic(
            commander, index.all_cards, owned_names, top_n=req.top,
            rng=var.rng, variety=var.variety, theme=theme,
        )
        result.suggestions = [UpgradeSuggestion(card=c, synergies=t) for c, t in suggestions]
        return result

    with ctx.reporter.progress("Asking Claude for upgrade suggestions..."):
        try:
            if ctx.settings.offline and ctx.settings.has_llm_key:
                raise RuntimeError("offline mode (COMMANDERAI_OFFLINE=1)")
            result.llm_text = find_suggestions_llm(
                commander, deck_cards or [], owned_names, index.all_cards, top_n=req.top,
                rng=var.rng, variety=var.variety, theme=theme,
            )
        except Exception as e:
            raise LLMError(str(e)) from e
    return result
