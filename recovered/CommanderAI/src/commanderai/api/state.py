"""Per-application state shared by the routers."""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Request

from commanderai.api.images import ImageIndex
from commanderai.api.schemas import MigrationStatus
from commanderai.errors import GoneError
from commanderai.reporting import CollectingReporter
from commanderai.services.context import ServiceContext
from commanderai.settings import Settings


@dataclass
class CachedBuild:
    result: Any               # services.build.BuildResult
    params: Any               # api.schemas.BuildParams (seed resolved)
    label: str
    expires_at: datetime


class BuildCache:
    """Recent build previews, so the UI can save one without re-sending the deck."""

    def __init__(self, max_entries: int = 50, ttl: timedelta = timedelta(hours=1)):
        self.max_entries = max_entries
        self.ttl = ttl
        self._items: OrderedDict[str, CachedBuild] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, result, params, label: str) -> tuple[str, datetime]:
        build_id = uuid.uuid4().hex
        expires = datetime.now(UTC) + self.ttl
        with self._lock:
            self._evict()
            self._items[build_id] = CachedBuild(result, params, label, expires)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
        return build_id, expires

    def get(self, build_id: str) -> CachedBuild:
        with self._lock:
            self._evict()
            item = self._items.get(build_id)
        if item is None:
            raise GoneError(
                "This build preview has expired. Build the deck again (the same seed gives the "
                "same deck), then save it.",
                build_id=build_id,
            )
        return item

    def _evict(self) -> None:
        now = datetime.now(UTC)
        for key in [k for k, v in self._items.items() if v.expires_at <= now]:
            del self._items[key]


@dataclass
class ApiState:
    settings: Settings
    images: ImageIndex
    sample_dir: Path
    builds: BuildCache = field(default_factory=BuildCache)
    migration: MigrationStatus | None = None

    def ctx(self) -> ServiceContext:
        return ServiceContext(settings=self.settings, reporter=CollectingReporter())


def get_state(request: Request) -> ApiState:
    return request.app.state.api


# Router parameter type: ``state: State`` injects the application state.
State = Annotated[ApiState, Depends(get_state)]
