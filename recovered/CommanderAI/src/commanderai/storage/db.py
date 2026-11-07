"""SQLite connection handling and schema migrations.

- One short-lived connection per operation (safe across threads / API requests).
- WAL journal mode for concurrent readers, foreign keys on.
- Schema versioned with ``PRAGMA user_version``; ``MIGRATIONS[i]`` upgrades the
  schema from version ``i`` to ``i + 1``.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS: list[str] = [
    # v0 -> v1
    """
    CREATE TABLE decks (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT    NOT NULL,
        commander         TEXT    NOT NULL,
        partner           TEXT,
        colors            TEXT    NOT NULL,
        theme             TEXT,
        seed              INTEGER,
        variety           REAL    NOT NULL DEFAULT 0,
        bracket           INTEGER,
        budget            REAL,
        card_count        INTEGER NOT NULL,
        total_price       REAL    NOT NULL,
        avg_cmc           REAL    NOT NULL,
        source            TEXT    NOT NULL,   -- cli | api | import | legacy
        collection_source TEXT,
        export_path       TEXT,
        export_format     TEXT,
        created_at        TEXT    NOT NULL,   -- ISO-8601 UTC
        updated_at        TEXT    NOT NULL,
        record            TEXT    NOT NULL    -- JSON DeckRecord
    );
    CREATE INDEX idx_decks_commander ON decks(commander);
    CREATE INDEX idx_decks_created   ON decks(created_at);
    CREATE INDEX idx_decks_export    ON decks(export_path);

    CREATE TABLE collections (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL UNIQUE,
        content     TEXT    NOT NULL,
        entries     INTEGER NOT NULL,
        copies      INTEGER NOT NULL,
        created_at  TEXT    NOT NULL,
        updated_at  TEXT    NOT NULL
    );

    -- One row per legacy .txt deck file seen by the txt -> SQLite migration.
    CREATE TABLE legacy_imports (
        path        TEXT    NOT NULL,
        sha256      TEXT    NOT NULL,
        deck_id     INTEGER REFERENCES decks(id) ON DELETE SET NULL,
        status      TEXT    NOT NULL,         -- imported | skipped | failed
        message     TEXT,
        imported_at TEXT    NOT NULL,
        PRIMARY KEY (path, sha256)
    );

    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)

_init_lock = threading.Lock()


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """A SQLite database file. Cheap to construct; schema created lazily."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._ready = False

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """A connection in a transaction (commit on success, rollback on error)."""
        self._ensure_schema()
        conn = self._open()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        if self._ready:
            return
        with _init_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._open()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Database {self.path} has schema v{version}, newer than this "
                        f"CommanderAI supports (v{SCHEMA_VERSION})."
                    )
                for target in range(version, SCHEMA_VERSION):
                    with conn:
                        conn.executescript(MIGRATIONS[target])
                        conn.execute(f"PRAGMA user_version = {target + 1}")
            finally:
                conn.close()
            self._ready = True

    @property
    def schema_version(self) -> int:
        with self.connect() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    # --- tiny key/value store --------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
