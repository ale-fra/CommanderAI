from fastapi import APIRouter, Response, status

from commanderai.api.registry import (
    CollectionRef,
    all_refs,
    ref_counts,
    ref_label,
    ref_source,
    resolve_ref,
)
from commanderai.api.routers import ERROR_RESPONSES
from commanderai.api.schemas import (
    CollectionCard,
    CollectionCreate,
    CollectionDetail,
    CollectionInfo,
    CollectionPreview,
    CollectionUpdate,
    ContentRequest,
    card_summary,
)
from commanderai.api.state import ApiState, State
from commanderai.deckbuilder.rules import is_legal_commander
from commanderai.errors import ReadOnlyError
from commanderai.services.collection import LoadedCollection, load_collection, parse_source
from commanderai.services.collections import (
    delete_collection,
    rename_collection,
    replace_collection,
    save_collection,
)
from commanderai.services.context import ServiceContext

router = APIRouter(prefix="/api/collections", tags=["collections"], responses=ERROR_RESPONSES)


def _info(ctx: ServiceContext, ref: CollectionRef) -> CollectionInfo:
    entries, copies = ref_counts(ctx, ref)
    return CollectionInfo(
        id=ref.id, kind=ref.kind, name=ref.name, description=ref.description,
        entries=entries, copies=copies, editable=ref.editable,
    )


def load_ref(state: ApiState, ctx: ServiceContext, collection_id: str) -> tuple[CollectionRef, LoadedCollection]:
    ref = resolve_ref(ctx, collection_id, state.sample_dir)
    loaded = load_collection(ctx, ref_source(ctx, ref), label=ref_label(ref))
    return ref, loaded


def _detail(state: ApiState, ctx: ServiceContext, collection_id: str) -> CollectionDetail:
    ref, loaded = load_ref(state, ctx, collection_id)
    return CollectionDetail(
        **_info(ctx, ref).model_dump(),
        unique_cards=len(loaded.cards),
        commanders=sum(1 for c in loaded.cards if is_legal_commander(c)),
        match=loaded.report,
    )


def _editable(state: ApiState, ctx: ServiceContext, collection_id: str) -> CollectionRef:
    ref = resolve_ref(ctx, collection_id, state.sample_dir)
    if not ref.editable:
        raise ReadOnlyError(f"'{ref.name}' is a built-in collection and can't be changed", id=ref.id)
    return ref


@router.get("", response_model=list[CollectionInfo])
def list_all(state: State) -> list[CollectionInfo]:
    ctx = state.ctx()
    return [_info(ctx, ref) for ref in all_refs(ctx, state.sample_dir)]


@router.post("/preview", response_model=CollectionPreview)
def preview(state: State, body: ContentRequest) -> CollectionPreview:
    """Parse and match a collection without saving it (upload dialog)."""
    ctx = state.ctx()
    loaded = load_collection(ctx, body.content, empty_message="No cards found in collection")
    return CollectionPreview(
        entries=len(loaded.entries),
        copies=sum(e.quantity for e in loaded.entries),
        unique_cards=len(loaded.cards),
        commanders=sum(1 for c in loaded.cards if is_legal_commander(c)),
        match=loaded.report,
    )


@router.post("", response_model=CollectionDetail, status_code=status.HTTP_201_CREATED)
def create(state: State, body: CollectionCreate) -> CollectionDetail:
    ctx = state.ctx()
    stored = save_collection(ctx, body.name, body.content)
    return _detail(state, ctx, f"stored:{stored.id}")


@router.get("/{collection_id}", response_model=CollectionDetail)
def get_one(state: State, collection_id: str) -> CollectionDetail:
    return _detail(state, state.ctx(), collection_id)


@router.get("/{collection_id}/cards", response_model=list[CollectionCard])
def cards(state: State, collection_id: str) -> list[CollectionCard]:
    """Every owned card with its quantity (the UI filters and sorts client-side)."""
    ctx = state.ctx()
    _, loaded = load_ref(state, ctx, collection_id)
    quantities: dict[str, int] = {}
    for entry in loaded.match.matched:
        if entry.card:
            quantities[entry.card.name] = quantities.get(entry.card.name, 0) + entry.quantity
    return [
        CollectionCard(**card_summary(card, state.images).model_dump(), quantity=quantities[card.name])
        for card in loaded.cards
    ]


@router.patch("/{collection_id}", response_model=CollectionDetail)
def update(state: State, collection_id: str, body: CollectionUpdate) -> CollectionDetail:
    ctx = state.ctx()
    ref = _editable(state, ctx, collection_id)
    if body.content is not None:
        replace_collection(ctx, ref.stored_id, body.content)
    if body.name is not None:
        rename_collection(ctx, ref.stored_id, body.name)
    return _detail(state, ctx, collection_id)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(state: State, collection_id: str) -> Response:
    ctx = state.ctx()
    ref = _editable(state, ctx, collection_id)
    delete_collection(ctx, ref.stored_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["load_ref", "parse_source", "router"]
