"""Runtime settings (paths, API key) resolved from the environment.

Unlike the module-level constants in :mod:`commanderai.config` — which are
frozen at import time and kept for backwards compatibility — a
:class:`Settings` object can be built at any moment (``Settings.from_env()``)
or constructed explicitly (tests, the API server), so services never depend on
import order.

Precedence: explicit constructor args > shell environment > project ``.env``
> built-in defaults.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

# Load a project-local .env once (shell environment still takes precedence).
load_dotenv(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    decks_dir: Path
    default_collection: Path
    cache_dir: Path
    db_path: Path
    anthropic_api_key: str = ""
    offline: bool = False          # COMMANDERAI_OFFLINE=1: never call external services

    @property
    def oracle_cards_path(self) -> Path:
        return self.cache_dir / "oracle_cards.json"

    @property
    def has_llm_key(self) -> bool:
        return bool(self.anthropic_api_key)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            decks_dir=Path(env.get("COMMANDERAI_DECKS_DIR", PROJECT_DIR / "decks")),
            default_collection=Path(
                env.get("COMMANDERAI_COLLECTION", PROJECT_DIR / "data" / "my_collection.txt")
            ),
            cache_dir=Path(env.get("COMMANDERAI_CACHE", Path.home() / ".commanderai")),
            db_path=Path(env.get("COMMANDERAI_DB", PROJECT_DIR / "data" / "commanderai.db")),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            offline=env.get("COMMANDERAI_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on"),
        )

    def with_overrides(self, **changes) -> Settings:
        return replace(self, **changes)


def get_settings() -> Settings:
    """Settings from the current environment (re-read on every call)."""
    return Settings.from_env()
