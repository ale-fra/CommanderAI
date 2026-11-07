from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response, status

from commanderai.api.convert import deck_detail, deck_summary_dto
from commanderai.api.routers import ERROR_RESPONSES
from commanderai.api.schemas import (
    DeckDetail,
    DeckImportRequest,
    DeckImportResponse,
    DeckList,
    DeckUpdate,
    ExportFormat,
    SaveBuildRequest,
)
from commanderai.api.state import State
from commanderai.services.deck_files import safe_deck_name
from commanderai.services.library import (
    add_record,
    count_decks,
    delete_deck,
    export_deck,
    get_deck,
    import_deck,
    list_decks,
    record_from_build,
    update_deck,
)

router = APIRouter(prefix="/api/decks", tags=["decks"], responses=ERROR_RESPONSES)


@router.get("", response_model=DeckList)
def list_all(
    state: State,
    commander: str | None = None,
    source: str | None = None,
    q: Annotated[str | None,
    Query(description="Search in deck name and commander names")] = None,
    limit: Annotated[int,
    Query(ge=1, le=500)] = 50,
    offset: Annotated[int,
    Query(ge=0)] = 0,
) -> DeckList:
    ctx = state.ctx()
    items = list_decks(ctx, commander=commander, source=source, query=q, limit=limit, offset=offset)
    return DeckList(
        total=count_decks(ctx, commander=commander, source=source, query=q),
        items=[deck_summary_dto(d, state.images) for d in items],
    )


@router.post("", response_model=DeckDetail, status_code=status.HTTP_201_CREATED)
def save(state: State, body: SaveBuildRequest) -> DeckDetail:
    """Save a build preview (from ``POST /api/builds``) to the deck library."""
    cached = state.builds.get(body.build_id)
    record = record_from_build(cached.result, name=body.name or None, source="api")
    record.build = {**(record.build or {}), "api_params": cached.params.model_dump()}
    saved = add_record(state.ctx(), record)
    return deck_detail(state, saved)


@router.post("/import", response_model=DeckImportResponse, status_code=status.HTTP_201_CREATED)
def import_(state: State, body: DeckImportRequest) -> DeckImportResponse:
    """Import a deck: a CommanderAI JSON export, or any text decklist."""
    record, unknown = import_deck(state.ctx(), body.content, name=body.name, filename=body.filename)
    return DeckImportResponse(deck=deck_detail(state, record), unknown_cards=unknown)


@router.get("/{deck_id}", response_model=DeckDetail)
def get_one(state: State, deck_id: int) -> DeckDetail:
    return deck_detail(state, get_deck(state.ctx(), deck_id))


@router.patch("/{deck_id}", response_model=DeckDetail)
def update(state: State, deck_id: int, body: DeckUpdate) -> DeckDetail:
    return deck_detail(state, update_deck(state.ctx(), deck_id, name=body.name, notes=body.notes))


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(state: State, deck_id: int) -> Response:
    delete_deck(state.ctx(), deck_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{deck_id}/export",
    response_class=Response,
    responses={200: {"content": {"text/plain": {}, "application/json": {}}}},
)
def export(state: State, deck_id: int, format: ExportFormat = "json") -> Response:
    """Download a deck as a JSON document (re-importable) or a text decklist."""
    record = get_deck(state.ctx(), deck_id)
    text = export_deck(record, format)
    ext, media = ("json", "application/json") if format == "json" else ("txt", "text/plain")
    filename = f"{safe_deck_name(record.name) or 'deck'}-{format}.{ext}"
    ascii_name = filename.encode("ascii", "ignore").decode() or f"deck-{format}.{ext}"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=text,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )
