"""Deck library: the SQLite deck database as the single source of truth.

Use-cases:
- save a build (CLI and API), list / get / rename / delete decks
- export a deck (JSON document, or any text format) and import one back
- migrate legacy ``decks/*.txt`` files into the database (automatically once,
  on first use of the library, and on demand via ``migrate_legacy_decks``)
- previously built card lists for a commander (LLM "build something different")

Every ``.txt`` file the library knows about is tracked in the
``legacy_imports`` table by (path, sha256): files written by the CLI are
recorded as ``exported``, migrated ones as ``imported`` (or ``failed``), so a
file is never imported twice and deleted decks are never resurrected.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from commanderai.data.card_index import CardIndex
from commanderai.deckbuilder.mana_base import make_basic_land
from commanderai.deckbuilder.partner import can_partner
from commanderai.deckbuilder.rules import is_legal_commander
from commanderai.deckbuilder.slots import classify_card
from commanderai.errors import DeckNotFoundError, InvalidRequestError, UnprocessableError
from commanderai.models import Card, Deck, DeckPick, DeckSlot
from commanderai.services.context import ServiceContext
from commanderai.services.deck_files import render_deck
from commanderai.settings import Settings
from commanderai.storage import Database, DeckRecord, DeckRepository, DeckSummary
from commanderai.storage.models import DECK_EXPORT_FORMAT, RECORD_SCHEMA_VERSION

LEGACY_MIGRATION_KEY = "legacy_txt_migration"
EXPORT_FORMATS = ("json", "text", "mtgo", "moxfield", "archidekt")

_BASIC_COLORS = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}

_databases: dict[str, Database] = {}


class DeckImportError(UnprocessableError):
    code = "deck_import_failed"


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------

def database(settings: Settings) -> Database:
    """The (cached) Database for the configured path."""
    key = str(settings.db_path.resolve())
    db = _databases.get(key)
    if db is None:
        db = _databases[key] = Database(settings.db_path)
    return db


def deck_repository(ctx: ServiceContext) -> DeckRepository:
    return DeckRepository(database(ctx.settings))


def _repo(ctx: ServiceContext, migrate: bool = True) -> DeckRepository:
    if migrate:
        ensure_legacy_migrated(ctx)
    return deck_repository(ctx)


# ---------------------------------------------------------------------------
# Saving builds
# ---------------------------------------------------------------------------

def record_from_build(
    result,  # services.build.BuildResult (imported lazily to avoid a cycle)
    *,
    name: str | None = None,
    source: str = "api",
    export_path: Path | None = None,
    export_format: str | None = None,
) -> DeckRecord:
    build = result.model_dump(mode="json", exclude={"deck": True, "request": {"collection_text"}})
    deck = result.deck
    return DeckRecord(
        name=name or " + ".join(c.name for c in deck.commanders),
        source=source,
        deck=deck,
        build=build,
        collection_source=result.match.source,
        export_path=str(export_path.resolve()) if export_path else None,
        export_format=export_format,
    )


def save_build(
    ctx: ServiceContext,
    result,
    *,
    name: str | None = None,
    source: str = "api",
    export_path: Path | None = None,
    export_format: str | None = None,
) -> DeckRecord:
    """Store a BuildResult; returns the saved record (with its id)."""
    record = record_from_build(
        result, name=name, source=source, export_path=export_path, export_format=export_format
    )
    return _repo(ctx).add(record)


def mark_exported(ctx: ServiceContext, record: DeckRecord, path: Path) -> None:
    """Remember a text file written for a stored deck so migration never re-imports it."""
    deck_repository(ctx).record_legacy(
        str(path.resolve()), _sha256(path.read_bytes()), "exported", deck_id=record.id
    )


# ---------------------------------------------------------------------------
# Reading / managing
# ---------------------------------------------------------------------------

def list_decks(
    ctx: ServiceContext,
    *,
    commander: str | None = None,
    source: str | None = None,
    query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[DeckSummary]:
    return _repo(ctx).list(
        commander=commander, source=source, query=query, limit=limit, offset=offset
    )


def count_decks(
    ctx: ServiceContext,
    *,
    commander: str | None = None,
    source: str | None = None,
    query: str | None = None,
) -> int:
    return _repo(ctx).count(commander=commander, source=source, query=query)


def add_record(ctx: ServiceContext, record: DeckRecord) -> DeckRecord:
    """Store a prepared record (e.g. a build record with extra API metadata)."""
    return _repo(ctx).add(record)


def get_deck(ctx: ServiceContext, deck_id: int) -> DeckRecord:
    record = _repo(ctx).get(deck_id)
    if record is None:
        raise DeckNotFoundError(f"Deck #{deck_id} not found", id=deck_id)
    return record


def rename_deck(ctx: ServiceContext, deck_id: int, name: str) -> DeckRecord:
    return update_deck(ctx, deck_id, name=name)


def update_deck(
    ctx: ServiceContext, deck_id: int, *, name: str | None = None, notes: str | None = None
) -> DeckRecord:
    """Change a deck's name and/or notes."""
    record = get_deck(ctx, deck_id)
    changes: dict = {}
    if name is not None:
        name = name.strip()
        if not name:
            raise InvalidRequestError("Deck name cannot be empty")
        changes["name"] = name
    if notes is not None:
        changes["notes"] = notes
    if not changes:
        return record
    return _repo(ctx, migrate=False).update(record.model_copy(update=changes))


def delete_deck(ctx: ServiceContext, deck_id: int) -> DeckRecord:
    record = get_deck(ctx, deck_id)
    _repo(ctx, migrate=False).delete(deck_id)
    return record


def prior_card_lists(ctx: ServiceContext, commander_name: str) -> list[list[str]]:
    """Non-land, non-basic card names of every stored deck for this commander."""
    decks = []
    for rec in _repo(ctx).by_commander(commander_name):
        commanders = {c.name for c in rec.deck.commanders}
        names = [
            p.card.name for p in rec.deck.cards
            if p.slot != DeckSlot.LAND
            and p.card.name not in commanders
            and p.card.name not in _BASIC_COLORS
        ]
        if names:
            decks.append(names)
    return decks


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------

def export_deck(record: DeckRecord, fmt: str = "json", verbose: bool = False) -> str:
    """Serialize a stored deck: ``json`` (re-importable document) or a text format."""
    if fmt == "json":
        doc = {
            "format": DECK_EXPORT_FORMAT,
            "version": RECORD_SCHEMA_VERSION,
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "deck": json.loads(
                record.model_dump_json(exclude={"id", "export_path", "export_format"})
            ),
        }
        return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if fmt not in EXPORT_FORMATS:
        raise InvalidRequestError(
            f"Unknown format '{fmt}'. Options: {', '.join(EXPORT_FORMATS)}", format=fmt
        )
    return render_deck(record.deck, fmt, verbose)


def import_deck(
    ctx: ServiceContext,
    content: str,
    *,
    name: str | None = None,
    filename: str | None = None,
) -> tuple[DeckRecord, list[str]]:
    """Import a deck from a JSON export document or a text decklist.

    Returns the stored record and the list of unknown card names skipped (text
    imports only).
    """
    if content.lstrip().startswith("{"):
        record = _record_from_json(content)
        record = record.model_copy(update={
            "source": "import", "name": name or record.name,
            "created_at": None, "export_path": None, "export_format": None,
        })
        return _repo(ctx).add(record), []

    parsed = parse_deck_text(content, ctx.catalog())
    default_name = Path(filename).stem if filename else parsed.deck.commander.name
    record = DeckRecord(
        name=name or default_name,
        source="import",
        deck=parsed.deck,
        collection_source=filename,
    )
    return _repo(ctx).add(record), parsed.unknown


def _record_from_json(content: str) -> DeckRecord:
    try:
        doc = json.loads(content)
    except json.JSONDecodeError as e:
        raise DeckImportError(f"Invalid JSON: {e}") from None
    if not isinstance(doc, dict) or doc.get("format") != DECK_EXPORT_FORMAT:
        raise DeckImportError(f"Not a CommanderAI deck export (expected format '{DECK_EXPORT_FORMAT}')")
    if doc.get("version", 0) > RECORD_SCHEMA_VERSION:
        raise DeckImportError(
            f"Deck export version {doc.get('version')} is newer than supported ({RECORD_SCHEMA_VERSION})"
        )
    try:
        return DeckRecord.model_validate(doc.get("deck") or {})
    except ValidationError as e:
        raise DeckImportError(f"Invalid deck document: {e.error_count()} error(s)",
                              details=[str(err["loc"]) + ": " + err["msg"] for err in e.errors()[:10]]) from None


# ---------------------------------------------------------------------------
# Text decklist parsing (all formats the CLI has ever written)
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^=== Commanders?:\s*(.+?)\s*===$")
_SECTION_RE = re.compile(r"^---\s*(.+?)(?:\s*\((\d+)\))?\s*---$")
_CARD_RE = re.compile(r"^(\d+)x?\s+(.+)$")
_TAG_RE = re.compile(r"\s*\[([^\]]+)\]\s*$")


@dataclass
class ParsedDeck:
    deck: Deck
    unknown: list[str] = field(default_factory=list)


@dataclass
class _Line:
    qty: int
    name: str
    slot: DeckSlot | None
    reason: str
    commander_mark: bool


def parse_deck_text(text: str, index: CardIndex) -> ParsedDeck:
    """Parse a decklist in the grouped text, Archidekt, Moxfield, MTGO or plain
    format into a Deck. Commanders come from the ``=== Commander ===`` header,
    ``[Commander]`` / ``*CMDR*`` markers, or — for plain lists — the first line
    (plus the second when the two can legally partner)."""
    header: list[str] = []
    lines: list[_Line] = []
    strategy = ""
    upgrades: list[str] = []
    section_slot: DeckSlot | None = None
    section = "cards"

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        if m := _HEADER_RE.match(line):
            header = [n.strip() for n in m.group(1).split(" + ") if n.strip()]
            continue
        if m := _SECTION_RE.match(line):
            label = m.group(1).strip().upper()
            if label in DeckSlot.__members__:
                section, section_slot = "cards", DeckSlot(label)
            elif "UPGRADE" in label:
                section = "upgrades"
            else:
                section = "other"
            continue
        if line.startswith("Strategy:"):
            strategy = line[len("Strategy:"):].strip()
            continue
        if section == "upgrades":
            if line.startswith("- "):
                upgrades.append(line[2:].strip())
            continue
        if section == "other":
            continue
        m = _CARD_RE.match(line)
        if not m:
            continue
        rest, reason = m.group(2), ""
        if "  // " in rest:
            rest, reason = rest.split("  // ", 1)
        marker = "*CMDR*" in rest
        rest = rest.replace("*CMDR*", "")
        tag = None
        if t := _TAG_RE.search(rest):
            tag, rest = t.group(1).strip(), rest[: t.start()]
        rest = re.split(r"\s+\{", rest, maxsplit=1)[0].strip()
        slot = section_slot
        if tag:
            if tag.lower() == "commander":
                marker = True
            elif tag.upper() in DeckSlot.__members__:
                slot = DeckSlot(tag.upper())
        lines.append(_Line(int(m.group(1)), rest, slot, reason.strip(), marker))

    unknown: list[str] = []

    def lookup(name: str) -> Card | None:
        card = index.get(name)
        if card is None and name not in unknown:
            unknown.append(name)
        return card

    # --- commanders ---
    commander_names = header or [ln.name for ln in lines if ln.commander_mark]
    if not commander_names and lines:
        first = index.get(lines[0].name)
        if first and is_legal_commander(first):
            commander_names = [lines[0].name]
            if len(lines) > 1:
                second = index.get(lines[1].name)
                if second and can_partner(first, second):
                    commander_names.append(lines[1].name)
    if not commander_names:
        raise DeckImportError("Could not identify the commander (no header, marker, or leading commander line)")

    commanders: list[Card] = []
    for name in commander_names[:2]:
        card = index.get(name)
        if card is None:
            raise DeckImportError(f"Commander '{name}' not found in the card catalog", name=name)
        commanders.append(card)

    # Drop the commander lines from the 99 (once each).
    remaining = set(commander_names[:2])
    body: list[_Line] = []
    for ln in lines:
        if ln.name in remaining:
            remaining.discard(ln.name)
            continue
        body.append(ln)

    picks: list[DeckPick] = []
    for ln in body:
        if ln.name in _BASIC_COLORS:
            card = make_basic_land(_BASIC_COLORS[ln.name])
        else:
            card = lookup(ln.name)
        if card is None:
            continue
        slot = ln.slot or classify_card(card)
        for _ in range(max(ln.qty, 1)):
            picks.append(DeckPick(card=card.model_copy() if ln.name in _BASIC_COLORS else card,
                                  slot=slot, reason=ln.reason))

    deck = Deck(
        commander=commanders[0],
        partner=commanders[1] if len(commanders) > 1 else None,
        cards=picks,
        strategy_summary=strategy,
        upgrade_suggestions=upgrades,
    )
    return ParsedDeck(deck=deck, unknown=unknown)


# ---------------------------------------------------------------------------
# Legacy txt -> SQLite migration
# ---------------------------------------------------------------------------

class MigrationItem(BaseModel):
    path: str
    status: str                      # imported | failed
    deck_id: int | None = None
    message: str | None = None


class MigrationReport(BaseModel):
    directory: str
    scanned: int = 0
    imported: list[MigrationItem] = Field(default_factory=list)
    failed: list[MigrationItem] = Field(default_factory=list)
    already_known: int = 0


def ensure_legacy_migrated(ctx: ServiceContext) -> MigrationReport | None:
    """Run the one-time txt -> SQLite migration if it hasn't run for this database."""
    db = database(ctx.settings)
    if db.get_meta(LEGACY_MIGRATION_KEY):
        return None
    report = migrate_legacy_decks(ctx)
    db.set_meta(LEGACY_MIGRATION_KEY, datetime.now(UTC).isoformat())
    return report


def migrate_legacy_decks(
    ctx: ServiceContext, directory: Path | None = None, retry_failed: bool = False
) -> MigrationReport:
    """Import every not-yet-known ``*.txt`` deck file from the decks directory.

    Files are identified by (resolved path, sha256): an edited file counts as new.
    With ``retry_failed``, files that failed to import before are tried again.
    """
    directory = directory or ctx.settings.decks_dir
    repo = deck_repository(ctx)
    report = MigrationReport(directory=str(directory))
    if not directory.exists():
        return report

    files = sorted(directory.glob("*.txt"), key=lambda p: (p.stat().st_mtime, p.name))
    report.scanned = len(files)
    known_exports = repo.export_paths()
    for path in files:
        resolved = str(path.resolve())
        data = path.read_bytes()
        sha = _sha256(data)
        if resolved in known_exports or repo.legacy_seen(resolved, sha, include_failed=not retry_failed):
            report.already_known += 1
            continue
        try:
            parsed = parse_deck_text(data.decode("utf-8"), ctx.catalog())
            created = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            record = repo.add(DeckRecord(
                name=path.stem,
                source="legacy",
                created_at=created,
                deck=parsed.deck,
                export_path=resolved,
                export_format=_guess_format(data.decode("utf-8")),
                notes=(f"Migrated from {path.name}"
                       + (f"; unknown cards skipped: {', '.join(parsed.unknown)}" if parsed.unknown else "")),
            ))
            repo.record_legacy(resolved, sha, "imported", deck_id=record.id)
            report.imported.append(MigrationItem(path=resolved, status="imported", deck_id=record.id,
                                                 message=", ".join(parsed.unknown) or None))
        except (DeckImportError, UnicodeDecodeError) as e:
            message = getattr(e, "message", str(e))
            repo.record_legacy(resolved, sha, "failed", message=message)
            report.failed.append(MigrationItem(path=resolved, status="failed", message=message))

    rep = ctx.reporter
    if report.imported:
        rep.success(
            "library.migrated",
            f"Imported {len(report.imported)} legacy deck file(s) from {directory} into the deck database",
            count=len(report.imported), directory=str(directory),
            decks=[{"path": i.path, "id": i.deck_id} for i in report.imported],
        )
    for item in report.failed:
        rep.warning(
            "library.migration_failed",
            f"Could not import {Path(item.path).name}: {item.message}",
            path=item.path, message=item.message,
        )
    return report


def _guess_format(text: str) -> str:
    if "=== Commander" in text:
        return "text"
    if "[Commander]" in text:
        return "archidekt"
    if "*CMDR*" in text:
        return "moxfield"
    return "mtgo"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
