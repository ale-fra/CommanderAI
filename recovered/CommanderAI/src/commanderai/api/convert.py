"""Builds and stored decks → API shapes (shared by the builds and decks routers)."""

from __future__ import annotations

from commanderai.api.images import ImageIndex
from commanderai.api.registry import ref_for_path
from commanderai.api.schemas import (
    BuildParams,
    BuildReport,
    BuildResultDTO,
    DeckDetail,
    DeckSummaryDTO,
    deck_view,
)
from commanderai.api.state import ApiState
from commanderai.models import Deck
from commanderai.services.analysis import deck_stats, deck_validation_errors, tokens_for_cards
from commanderai.storage import DeckRecord, DeckSummary


def _targets(quotas: dict[str, int] | None, lands: int | None) -> dict[str, int] | None:
    if not quotas:
        return None
    targets = dict(quotas)
    if lands is not None:
        targets["LAND"] = lands
    return targets


def _tokens(deck: Deck):
    return tokens_for_cards([p.card for p in deck.cards] + deck.commanders)


def build_result_dto(result, params: BuildParams, images: ImageIndex) -> BuildResultDTO:
    report = BuildReport.model_validate(result.model_dump(exclude={"deck", "request"}))
    return BuildResultDTO(
        params=params,
        deck=deck_view(result.deck, images),
        stats=deck_stats(result.deck, _targets(result.quotas, result.lands)),
        tokens=_tokens(result.deck),
        report=report,
    )


def _params_from_record(state: ApiState, record: DeckRecord) -> BuildParams | None:
    """Parameters that repeat this build from the UI, when they can be recovered."""
    build = record.build or {}
    if build.get("api_params"):
        return BuildParams.model_validate(build["api_params"])
    request = build.get("request")
    if not request:
        return None
    if request.get("collection_id") is not None:
        collection = f"stored:{request['collection_id']}"
    else:
        collection = ref_for_path(state.ctx(), request.get("collection"), state.sample_dir)
    if collection is None:
        return None
    return BuildParams(
        collection=collection,
        commander=request.get("commander"),
        partner=request.get("partner"),
        theme=request.get("theme"),
        colors=request.get("colors"),
        lands=request.get("lands", 37),
        variety=request.get("variety", 0.0),
        seed=build.get("seed"),
        budget=request.get("budget"),
        bracket=request.get("bracket"),
    )


def deck_detail(state: ApiState, record: DeckRecord) -> DeckDetail:
    build = record.build or None
    report = BuildReport.model_validate(build) if build else None
    targets = _targets(build.get("quotas"), build.get("lands")) if build else None
    return DeckDetail(
        id=record.id or 0,
        name=record.name,
        source=record.source,
        created_at=record.created_at or "",
        updated_at=record.updated_at or "",
        notes=record.notes,
        collection_source=record.collection_source,
        export_path=record.export_path,
        export_format=record.export_format,
        deck=deck_view(record.deck, state.images),
        stats=deck_stats(record.deck, targets),
        tokens=_tokens(record.deck),
        validation_errors=deck_validation_errors(record.deck),
        report=report,
        params=_params_from_record(state, record),
    )


def deck_summary_dto(summary: DeckSummary, images: ImageIndex) -> DeckSummaryDTO:
    return DeckSummaryDTO(
        **summary.model_dump(exclude={"export_format"}),
        commander_image=images.images(summary.commander).front,
    )
