"""Static configuration and backwards-compatible path constants.

Path/API-key constants are snapshotted from :class:`commanderai.settings.Settings`
at import time. New code should take a ``Settings`` object instead (see
:mod:`commanderai.settings`), which can be resolved or overridden at runtime.
"""

from commanderai.settings import PROJECT_DIR, Settings

_ENV_SETTINGS = Settings.from_env()

DECKS_DIR = _ENV_SETTINGS.decks_dir
DEFAULT_COLLECTION = _ENV_SETTINGS.default_collection

CACHE_DIR = _ENV_SETTINGS.cache_dir
ORACLE_CARDS_PATH = _ENV_SETTINGS.oracle_cards_path
DB_PATH = _ENV_SETTINGS.db_path
BULK_DATA_MAX_AGE_DAYS = 7

ANTHROPIC_API_KEY = _ENV_SETTINGS.anthropic_api_key
LLM_MODEL = "claude-sonnet-4-20250514"

DECK_SIZE = 100
DEFAULT_LAND_COUNT = 37

SLOT_QUOTAS = {
    "LAND": 37,
    "RAMP": 10,
    "DRAW": 10,
    "REMOVAL": 8,
    "WIPE": 4,
    "THREAT": 20,
    "UTILITY": 10,
}

SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data"
SCRYFALL_USER_AGENT = "CommanderAI/0.7.0"

CANDIDATES_PER_SLOT_MULTIPLIER = 3
MAX_TOTAL_CANDIDATES = 300

__all__ = [
    "PROJECT_DIR", "DECKS_DIR", "DEFAULT_COLLECTION", "CACHE_DIR", "ORACLE_CARDS_PATH",
    "DB_PATH", "BULK_DATA_MAX_AGE_DAYS", "ANTHROPIC_API_KEY", "LLM_MODEL", "DECK_SIZE",
    "DEFAULT_LAND_COUNT", "SLOT_QUOTAS", "SCRYFALL_BULK_URL", "SCRYFALL_USER_AGENT",
    "CANDIDATES_PER_SLOT_MULTIPLIER", "MAX_TOTAL_CANDIDATES",
]
