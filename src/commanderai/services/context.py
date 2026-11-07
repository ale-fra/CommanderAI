"""Per-operation context shared by all services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from commanderai.catalog import load_catalog
from commanderai.data.card_index import CardIndex
from commanderai.reporting import Reporter
from commanderai.settings import Settings, get_settings


@dataclass
class ServiceContext:
    """Settings + reporter + a lazily-loaded card catalog.

    The catalog is loaded on first use (not at construction) so that input
    validation errors surface before the (comparatively slow) catalog load —
    matching the CLI's historical ordering of messages.
    """

    settings: Settings = field(default_factory=get_settings)
    reporter: Reporter = field(default_factory=Reporter)
    catalog_loader: Callable[[Settings], CardIndex] | None = None
    _catalog: CardIndex | None = field(default=None, init=False, repr=False)

    def catalog(self) -> CardIndex:
        if self._catalog is None:
            with self.reporter.progress("Loading card database..."):
                loader = self.catalog_loader or (lambda s: load_catalog(s.oracle_cards_path))
                index = loader(self.settings)
            self.reporter.detail(
                "catalog.loaded",
                f"Loaded {len(index.all_cards)} Commander-legal cards",
                count=len(index.all_cards),
            )
            self._catalog = index
        return self._catalog
