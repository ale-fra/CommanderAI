from fastapi import APIRouter

from commanderai.api.convert import build_result_dto
from commanderai.api.registry import ref_label, resolve_ref
from commanderai.api.routers import ERROR_RESPONSES
from commanderai.api.schemas import BuildParams, BuildResponse
from commanderai.api.state import State
from commanderai.services.build import BuildRequest, build_deck

router = APIRouter(prefix="/api/builds", tags=["builds"], responses=ERROR_RESPONSES)


@router.post("", response_model=BuildResponse)
def build(state: State, params: BuildParams) -> BuildResponse:
    """Build a deck preview (not saved). Save it with ``POST /api/decks``.

    The response echoes the parameters with the seed actually used, so sending
    them again reproduces the same deck.
    """
    ctx = state.ctx()
    ref = resolve_ref(ctx, params.collection, state.sample_dir)
    request = BuildRequest(
        collection=ref.path if ref.stored_id is None else None,
        collection_id=ref.stored_id,
        collection_label=ref_label(ref),
        commander=params.commander or None,
        partner=params.partner or None,
        theme=params.theme or None,
        colors=params.colors or None,
        lands=params.lands,
        variety=params.variety,
        seed=params.seed,
        budget=params.budget,
        bracket=params.bracket,
        use_llm=False,   # AI features are not exposed in the UI
    )
    result = build_deck(ctx, request)
    resolved = params.model_copy(update={"seed": result.seed})
    build_id, expires = state.builds.put(result, resolved, ref_label(ref))
    return BuildResponse(
        build_id=build_id,
        expires_at=expires.isoformat(timespec="seconds"),
        result=build_result_dto(result, resolved, state.images),
    )
