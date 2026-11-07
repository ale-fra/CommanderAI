"""Repositories over the SQLite database."""

from __future__ import annotations

import sqlite3

from commanderai.storage.db import Database, utcnow
from commanderai.storage.models import (
    DeckRecord,
    DeckSummary,
    LegacyImportRow,
    StoredCollection,
)

_SUMMARY_COLUMNS = (
    "id, name, commander, partner, colors, theme, seed, variety, bracket, budget, "
    "card_count, total_price, avg_cmc, source, collection_source, export_path, "
    "export_format, created_at, updated_at"
)


class DeckRepository:
    def __init__(self, db: Database):
        self.db = db

    # --- writes ---------------------------------------------------------------

    def add(self, record: DeckRecord) -> DeckRecord:
        """Insert a record; returns a copy with ``id`` and timestamps set."""
        now = utcnow()
        rec = record.model_copy(update={
            "id": None,
            "created_at": record.created_at or now,
            "updated_at": now,
        })
        cols = rec.columns()
        cols.update(created_at=rec.created_at, updated_at=rec.updated_at,
                    record=rec.model_dump_json(exclude={"id"}))
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        with self.db.connect() as conn:
            cur = conn.execute(f"INSERT INTO decks ({names}) VALUES ({marks})", tuple(cols.values()))
            new_id = cur.lastrowid
        return rec.model_copy(update={"id": new_id})

    def update(self, record: DeckRecord) -> DeckRecord:
        """Persist changes to an existing record (name, notes, export info, …)."""
        if record.id is None:
            raise ValueError("record has no id")
        rec = record.model_copy(update={"updated_at": utcnow()})
        cols = rec.columns()
        cols.update(updated_at=rec.updated_at, record=rec.model_dump_json(exclude={"id"}))
        assignments = ", ".join(f"{k} = ?" for k in cols)
        with self.db.connect() as conn:
            cur = conn.execute(
                f"UPDATE decks SET {assignments} WHERE id = ?", (*cols.values(), rec.id)
            )
            if cur.rowcount == 0:
                raise KeyError(rec.id)
        return rec

    def delete(self, deck_id: int) -> bool:
        with self.db.connect() as conn:
            return conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,)).rowcount > 0

    # --- reads ----------------------------------------------------------------

    def get(self, deck_id: int) -> DeckRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT id, record FROM decks WHERE id = ?", (deck_id,)).fetchone()
        return self._record(row) if row else None

    def list(
        self,
        *,
        commander: str | None = None,
        source: str | None = None,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        newest_first: bool = True,
    ) -> list[DeckSummary]:
        where, params = self._filters(commander, source, query)
        order = "DESC" if newest_first else "ASC"
        sql = f"SELECT {_SUMMARY_COLUMNS} FROM decks{where} ORDER BY created_at {order}, id {order}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [DeckSummary(**dict(r)) for r in rows]

    def count(
        self, *, commander: str | None = None, source: str | None = None, query: str | None = None
    ) -> int:
        where, params = self._filters(commander, source, query)
        with self.db.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM decks{where}", params).fetchone()[0]

    def by_commander(self, commander: str) -> list[DeckRecord]:
        """Full records for a commander (as primary or partner), oldest first."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, record FROM decks WHERE commander = ? OR partner = ? "
                "ORDER BY created_at, id",
                (commander, commander),
            ).fetchall()
        return [self._record(r) for r in rows]

    def export_paths(self) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT export_path FROM decks WHERE export_path IS NOT NULL").fetchall()
        return {r["export_path"] for r in rows}

    @staticmethod
    def _filters(
        commander: str | None, source: str | None, query: str | None = None
    ) -> tuple[str, list]:
        clauses, params = [], []
        if query:
            like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append(
                "(name LIKE ? ESCAPE '\\' OR commander LIKE ? ESCAPE '\\' OR partner LIKE ? ESCAPE '\\')"
            )
            params += [like, like, like]
        if commander:
            clauses.append("(commander = ? OR partner = ?)")
            params += [commander, commander]
        if source:
            clauses.append("source = ?")
            params.append(source)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    @staticmethod
    def _record(row: sqlite3.Row) -> DeckRecord:
        return DeckRecord.model_validate_json(row["record"]).model_copy(update={"id": row["id"]})

    # --- legacy txt migration bookkeeping -----------------------------------

    def legacy_seen(self, path: str, sha256: str, include_failed: bool = True) -> bool:
        """Whether this exact file version is already known (optionally ignoring failures)."""
        sql = "SELECT 1 FROM legacy_imports WHERE path = ? AND sha256 = ?"
        if not include_failed:
            sql += " AND status != 'failed'"
        with self.db.connect() as conn:
            return conn.execute(sql, (path, sha256)).fetchone() is not None

    def record_legacy(self, path: str, sha256: str, status: str,
                      deck_id: int | None = None, message: str | None = None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO legacy_imports(path, sha256, deck_id, status, message, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (path, sha256, deck_id, status, message, utcnow()),
            )

    def legacy_rows(self) -> list[LegacyImportRow]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM legacy_imports ORDER BY path, sha256").fetchall()
        return [LegacyImportRow(**dict(r)) for r in rows]


class CollectionRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, name: str, content: str, entries: int, copies: int) -> StoredCollection:
        now = utcnow()
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO collections(name, content, entries, copies, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, content, entries, copies, now, now),
            )
            new_id = cur.lastrowid
        return self.get(new_id)  # type: ignore[return-value]

    def replace_content(self, collection_id: int, content: str, entries: int, copies: int) -> bool:
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE collections SET content = ?, entries = ?, copies = ?, updated_at = ? WHERE id = ?",
                (content, entries, copies, utcnow(), collection_id),
            ).rowcount > 0

    def rename(self, collection_id: int, name: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE collections SET name = ?, updated_at = ? WHERE id = ?",
                (name, utcnow(), collection_id),
            ).rowcount > 0

    def get(self, collection_id: int, with_content: bool = True) -> StoredCollection | None:
        cols = "*" if with_content else "id, name, entries, copies, created_at, updated_at"
        with self.db.connect() as conn:
            row = conn.execute(f"SELECT {cols} FROM collections WHERE id = ?", (collection_id,)).fetchone()
        return StoredCollection(**dict(row)) if row else None

    def get_by_name(self, name: str) -> StoredCollection | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM collections WHERE name = ?", (name,)).fetchone()
        return StoredCollection(**dict(row)) if row else None

    def list(self) -> list[StoredCollection]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, name, entries, copies, created_at, updated_at FROM collections ORDER BY name"
            ).fetchall()
        return [StoredCollection(**dict(r)) for r in rows]

    def delete(self, collection_id: int) -> bool:
        with self.db.connect() as conn:
            return conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,)).rowcount > 0
