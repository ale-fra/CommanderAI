import json

from fastapi import APIRouter

from commanderai import __version__
from commanderai.api.registry import default_collection_id
from commanderai.api.routers import ERROR_RESPONSES
from commanderai.api.schemas import (
    CardDetail,
    CatalogStatus,
    DatabaseStatus,
    StatusResponse,
    VocabularyResponse,
    card_detail,
)
from commanderai.api.state import State
from commanderai.errors import CardNotFoundError
from commanderai.services.collections import list_collections
from commanderai.services.library import count_decks
from commanderai.services.reference import vocabulary

router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)


@router.get("/status", response_model=StatusResponse, tags=["system"])
def status(state: State) -> StatusResponse:
    ctx = state.ctx()
    snapshot = None
    provenance = state.settings.cache_dir / "provenance.json"
    if provenance.exists():
        snapshot = json.loads(provenance.read_text(encoding="utf-8")).get("bulk_metadata", {}).get("updated_at")
    return StatusResponse(
        version=__version__,
        offline=state.settings.offline,
        catalog=CatalogStatus(cards=len(ctx.catalog().all_cards), snapshot=snapshot),
        database=DatabaseStatus(decks=count_decks(ctx), collections=len(list_collections(ctx))),
        default_collection=default_collection_id(ctx, state.sample_dir),
        migration=state.migration,
    )


@router.get("/vocabulary", response_model=VocabularyResponse, tags=["system"])
def get_vocabulary() -> VocabularyResponse:
    return vocabulary()


# Card names can contain "/" (double-faced cards), so the name is a query parameter.
@router.get("/card", response_model=CardDetail, tags=["cards"])
def card(state: State, name: str) -> CardDetail:
    found = state.ctx().catalog().get(name)
    if not found:
        raise CardNotFoundError(f"Card '{name}' not found", name=name)
    return card_detail(found, state.images)
