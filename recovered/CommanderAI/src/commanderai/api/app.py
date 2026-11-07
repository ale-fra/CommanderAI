"""FastAPI application factory: the JSON API under /api plus the built web UI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from commanderai import __version__
from commanderai.api.images import image_index
from commanderai.api.registry import DEFAULT_SAMPLE_DIR
from commanderai.api.routers import builds, collections, commanders, decks, system
from commanderai.api.schemas import MigrationStatus
from commanderai.api.state import ApiState
from commanderai.errors import CommanderAIError
from commanderai.services.library import ensure_legacy_migrated
from commanderai.settings import PROJECT_DIR, Settings, get_settings

log = logging.getLogger("commanderai.api")

DEFAULT_WEB_DIST = PROJECT_DIR / "web" / "dist"


def _operation_id(route: APIRoute) -> str:
    return f"{route.tags[0] if route.tags else 'api'}_{route.name}"


def create_app(
    settings: Settings | None = None,
    web_dist: Path | None = DEFAULT_WEB_DIST,
    sample_dir: Path = DEFAULT_SAMPLE_DIR,
) -> FastAPI:
    settings = settings or get_settings()
    state = ApiState(settings=settings, images=image_index(settings.cache_dir), sample_dir=sample_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # One-time import of legacy decks/*.txt into the deck database.
        try:
            report = ensure_legacy_migrated(state.ctx())
            if report is not None:
                state.migration = MigrationStatus(
                    imported=len(report.imported), failed=len(report.failed)
                )
        except Exception:
            log.exception("legacy deck migration failed")
        yield

    app = FastAPI(
        title="CommanderAI",
        version=__version__,
        description="Build Commander decks from the cards you own. See docs/UI_PLAN.md.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.api = state

    # --- errors: one JSON shape for every failure -------------------------------
    @app.exception_handler(CommanderAIError)
    async def domain_error(_: Request, err: CommanderAIError) -> JSONResponse:
        return JSONResponse(status_code=err.status_code, content={"error": err.to_dict()})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, err: RequestValidationError) -> JSONResponse:
        details = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "code": "validation_error", "message": "Invalid request", "details": details, "data": {},
        }})

    for module in (system, collections, commanders, builds, decks):
        app.include_router(module.router)

    # --- static: card images and the web UI --------------------------------------------
    if state.images.directory.exists():
        app.mount("/api/images", _ImmutableStatic(directory=state.images.directory), name="images")

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                   include_in_schema=False)
    def api_not_found(path: str) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": {
            "code": "not_found", "message": f"No API endpoint /api/{path}", "details": [], "data": {}}})

    if web_dist is not None and (web_dist / "index.html").exists():
        app.mount("/assets", _ImmutableStatic(directory=web_dist / "assets"), name="assets")
        index = web_dist / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (web_dist / path).resolve()
            if path and file.is_file() and web_dist.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


class _ImmutableStatic(StaticFiles):
    """Static files with long-lived caching (content never changes for a given name)."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
