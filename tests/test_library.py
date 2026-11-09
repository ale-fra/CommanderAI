"""Deck database (SQLite) and deck-library service tests."""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from commanderai.data.card_index import CardIndex
from commanderai.errors import (
    CollectionNotFoundError,
    DeckNotFoundError,
    EmptyCollectionError,
    InvalidRequestError,
)
from commanderai.models import Card, Deck, DeckPick, DeckSlot
from commanderai.reporting import CollectingReporter
from commanderai.services.build import BuildRequest, build_deck
from commanderai.services.collections import (
    delete_collection,
    get_collection,
    list_collections,
    rename_collection,
    replace_collection,
    save_collection,
)
from commanderai.services.context import ServiceContext
from commanderai.services.deck_files import render_deck
from commanderai.services.library import (
    DeckImportError,
    database,
    delete_deck,
    export_deck,
    get_deck,
    import_deck,
    list_decks,
    mark_exported,
    migrate_legacy_decks,
    parse_deck_text,
    prior_card_lists,
    rename_deck,
    save_build,
)
from commanderai.settings import Settings
from commanderai.storage import Database
from commanderai.storage.db import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parent.parent
OFFLINE = ROOT / "tests/fixtures/integration/catalog"
SAMPLE = ROOT / "tests/fixtures/integration/collections"

@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        decks_dir=tmp_path / "decks",
        default_collection=SAMPLE / "expanded-collection.txt",
        cache_dir=OFFLINE,
        db_path=tmp_path / "lib.db",
        offline=True,
    )


def new_ctx(settings) -> ServiceContext:
    return ServiceContext(settings=settings, reporter=CollectingReporter())


@pytest.fixture
def ctx(settings) -> ServiceContext:
    return new_ctx(settings)


@pytest.fixture(scope="module")
def zaxara_result(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("build")
    s = Settings(decks_dir=tmp / "decks", default_collection=SAMPLE / "expanded-collection.txt",
                 cache_dir=OFFLINE, db_path=tmp / "unused.db", offline=True)
    return build_deck(ServiceContext(settings=s), BuildRequest(commander="Zaxara, the Exemplary"))


def names(deck: Deck) -> list[str]:
    return sorted(p.card.name for p in deck.cards)


# --- database ---------------------------------------------------------------------

def test_schema_created_and_versioned(tmp_path):
    db = Database(tmp_path / "x.db")
    assert db.schema_version == SCHEMA_VERSION
    tables = {r[0] for r in sqlite3.connect(tmp_path / "x.db").execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"decks", "collections", "legacy_imports", "meta"} <= tables
    # Re-opening an up-to-date database is a no-op.
    assert Database(tmp_path / "x.db").schema_version == SCHEMA_VERSION


def test_newer_schema_is_rejected(tmp_path):
    conn = sqlite3.connect(tmp_path / "future.db")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        _ = Database(tmp_path / "future.db").schema_version


# --- save / read / manage ------------------------------------------------------------

def test_save_and_get_roundtrip(ctx, zaxara_result):
    rec = save_build(ctx, zaxara_result, source="api")
    assert rec.id == 1 and rec.created_at
    loaded = get_deck(ctx, rec.id)
    assert loaded.deck == zaxara_result.deck          # full snapshot, exact
    assert loaded.build["request"]["commander"] == "Zaxara, the Exemplary"
    assert "collection_text" not in loaded.build["request"]
    assert loaded.build["notices"]                    # build log kept
    summary = list_decks(ctx)[0]
    assert summary.commander == "Zaxara, the Exemplary"
    assert summary.colors == "UBG"
    assert summary.card_count == 100
    assert summary.total_price == round(zaxara_result.deck.total_price, 2)


def test_list_order_filter_and_pagination(ctx, settings, zaxara_result):
    atarka = build_deck(new_ctx(settings), BuildRequest(commander="Fixture Dragon Commander"))
    first = save_build(ctx, zaxara_result)
    second = save_build(ctx, atarka)
    third = save_build(ctx, zaxara_result, name="Zaxara again")
    assert [d.id for d in list_decks(ctx)] == [third.id, second.id, first.id]   # newest first
    assert [d.id for d in list_decks(ctx, commander="Zaxara, the Exemplary")] == [third.id, first.id]
    assert [d.id for d in list_decks(ctx, limit=1, offset=1)] == [second.id]


def test_rename_and_delete(ctx, zaxara_result):
    rec = save_build(ctx, zaxara_result)
    assert rename_deck(ctx, rec.id, "  My Zaxara ").name == "My Zaxara"
    assert get_deck(ctx, rec.id).name == "My Zaxara"
    with pytest.raises(InvalidRequestError):
        rename_deck(ctx, rec.id, "   ")
    delete_deck(ctx, rec.id)
    with pytest.raises(DeckNotFoundError) as exc:
        get_deck(ctx, rec.id)
    assert exc.value.status_code == 404
    with pytest.raises(DeckNotFoundError):
        delete_deck(ctx, 999)


# --- export / import -------------------------------------------------------------------

def test_json_export_import_roundtrip(ctx, zaxara_result):
    rec = save_build(ctx, zaxara_result)
    doc = export_deck(rec, "json")
    data = json.loads(doc)
    assert data["format"] == "commanderai.deck" and data["version"] == 1
    assert "id" not in data["deck"] and "export_path" not in data["deck"]
    imported, unknown = import_deck(ctx, doc, name="Copy")
    assert unknown == []
    assert imported.id != rec.id and imported.source == "import" and imported.name == "Copy"
    assert imported.deck == rec.deck
    assert imported.build == rec.build


@pytest.mark.parametrize("content, match", [
    ("{not json", "Invalid JSON"),
    (json.dumps({"format": "other"}), "Not a CommanderAI deck export"),
    (json.dumps({"format": "commanderai.deck", "version": 99, "deck": {}}), "newer"),
    (json.dumps({"format": "commanderai.deck", "version": 1, "deck": {"name": "x"}}), "Invalid deck document"),
])
def test_bad_json_imports(ctx, content, match):
    with pytest.raises(DeckImportError, match=match):
        import_deck(ctx, content)


@pytest.mark.parametrize("fmt", ["text", "mtgo", "moxfield", "archidekt"])
def test_text_exports_match_cli_renderer(ctx, zaxara_result, fmt):
    rec = save_build(ctx, zaxara_result)
    assert export_deck(rec, fmt) == render_deck(zaxara_result.deck, fmt)


def test_unknown_export_format(ctx, zaxara_result):
    rec = save_build(ctx, zaxara_result)
    with pytest.raises(InvalidRequestError):
        export_deck(rec, "pdf")


@pytest.mark.parametrize("fmt, slots_preserved", [
    ("text", True), ("archidekt", True), ("moxfield", False), ("mtgo", False),
])
def test_parse_every_export_format(ctx, zaxara_result, fmt, slots_preserved):
    text = render_deck(zaxara_result.deck, fmt, verbose=True)
    parsed = parse_deck_text(text, ctx.catalog())
    assert parsed.unknown == []
    assert parsed.deck.commander.name == "Zaxara, the Exemplary"
    assert parsed.deck.size == 100
    assert names(parsed.deck) == names(zaxara_result.deck)
    assert round(parsed.deck.total_price, 2) == round(zaxara_result.deck.total_price, 2)
    if slots_preserved:
        original = sorted((p.card.name, p.slot) for p in zaxara_result.deck.cards)
        assert sorted((p.card.name, p.slot) for p in parsed.deck.cards) == original


def test_parse_partner_decklists():
    def legend(name, colors, kw):
        return Card(name=name, type_line="Legendary Creature — Human", color_identity=colors,
                    oracle_text="Partner", keywords=kw)
    a, b = legend("Alpha One", ["W"], ["Partner"]), legend("Beta Two", ["U"], ["Partner"])
    filler = Card(name="Some Spell", type_line="Instant", color_identity=["U"], oracle_text="Draw a card.")
    deck = Deck(commander=a, partner=b, cards=[DeckPick(card=filler, slot=DeckSlot.DRAW)])
    index = CardIndex([a, b, filler])
    for fmt in ("text", "moxfield", "archidekt", "mtgo"):
        parsed = parse_deck_text(render_deck(deck, fmt), index)
        assert (parsed.deck.commander.name, parsed.deck.partner.name) == ("Alpha One", "Beta Two"), fmt
        assert names(parsed.deck) == ["Some Spell"]


def test_text_import_reports_unknown_cards(ctx):
    rec, unknown = import_deck(ctx, "1 Zaxara, the Exemplary\n1 Sol Ring\n1 Not A Real Card\n",
                               filename="mine.txt")
    assert rec.name == "mine" and rec.source == "import"
    assert unknown == ["Not A Real Card"]
    assert names(rec.deck) == ["Sol Ring"]


def test_text_import_without_commander_fails(ctx):
    with pytest.raises(DeckImportError, match="commander"):
        import_deck(ctx, "1 Sol Ring\n1 Arcane Signet\n")


# --- legacy txt migration ----------------------------------------------------------

def _write_legacy(settings, zaxara_result) -> list[Path]:
    settings.decks_dir.mkdir(parents=True)
    files = []
    for i, fmt in enumerate(("text", "archidekt", "moxfield", "mtgo")):
        path = settings.decks_dir / f"old_{fmt}.txt"
        path.write_text(render_deck(zaxara_result.deck, fmt))
        os.utime(path, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
        files.append(path)
    (settings.decks_dir / "garbage.txt").write_text("hello\nworld\n")
    return files


def test_legacy_migration_runs_once_automatically(settings, zaxara_result):
    _write_legacy(settings, zaxara_result)
    ctx = new_ctx(settings)
    decks = list_decks(ctx)                      # first library use triggers the migration
    assert len(decks) == 4
    assert {d.source for d in decks} == {"legacy"}
    assert [d.name for d in decks] == ["old_mtgo", "old_moxfield", "old_archidekt", "old_text"]
    assert decks[-1].created_at.startswith("2023-11-14")           # file mtime preserved
    codes = [n.code for n in ctx.reporter.notices]
    assert "library.migrated" in codes and "library.migration_failed" in codes
    for d in decks:
        assert names(get_deck(ctx, d.id).deck) == names(zaxara_result.deck)

    # Second use: nothing happens.
    ctx2 = new_ctx(settings)
    assert len(list_decks(ctx2)) == 4
    assert not any(n.code.startswith("library.") for n in ctx2.reporter.notices)


def test_migration_never_duplicates_or_resurrects(settings, zaxara_result):
    ctx = new_ctx(settings)
    # A CLI-style build: stored + exported file marked as known.
    rec = save_build(ctx, zaxara_result, source="cli",
                     export_path=settings.decks_dir / "zaxara.txt", export_format="text")
    settings.decks_dir.mkdir(parents=True, exist_ok=True)
    path = settings.decks_dir / "zaxara.txt"
    path.write_text(render_deck(zaxara_result.deck, "text"))
    mark_exported(ctx, rec, path)

    report = migrate_legacy_decks(ctx)
    assert report.imported == [] and report.already_known == 1

    delete_deck(ctx, rec.id)                     # deleted deck: its file must not come back
    assert migrate_legacy_decks(ctx).imported == []
    assert list_decks(ctx) == []

    path.write_text(render_deck(zaxara_result.deck, "moxfield"))   # edited file = new version
    report = migrate_legacy_decks(ctx)
    assert len(report.imported) == 1


def test_failed_files_retried_only_on_request(settings, zaxara_result):
    settings.decks_dir.mkdir(parents=True)
    bad = settings.decks_dir / "bad.txt"
    bad.write_text("nothing useful\n")
    ctx = new_ctx(settings)
    assert len(migrate_legacy_decks(ctx).failed) == 1
    assert migrate_legacy_decks(ctx).failed == []                  # remembered
    assert len(migrate_legacy_decks(ctx, retry_failed=True).failed) == 1


# --- prior decks (LLM variety) come from the database ------------------------------

def test_prior_card_lists_from_database(ctx, zaxara_result):
    save_build(ctx, zaxara_result)
    lists = prior_card_lists(ctx, "Zaxara, the Exemplary")
    assert len(lists) == 1
    expected = [p.card.name for p in zaxara_result.deck.cards if p.slot != DeckSlot.LAND]
    assert lists[0] == expected
    assert prior_card_lists(ctx, "Fixture Dragon Commander") == []


def test_build_uses_stored_decks_as_prior_builds(ctx, zaxara_result):
    save_build(ctx, zaxara_result)
    save_build(ctx, zaxara_result)
    build_deck(ctx, BuildRequest(commander="Zaxara, the Exemplary", use_llm=True, seed=3))
    prior = [n for n in ctx.reporter.notices if n.code == "llm.prior_decks"]
    assert prior and prior[0].data["count"] == 2


# --- stored collections ------------------------------------------------------------------

def test_stored_collections_crud(ctx):
    text = (SAMPLE / "precons" / "first-flight.txt").read_text()
    stored = save_collection(ctx, "First Flight", text)
    assert stored.id == 1 and stored.entries == 72 and stored.copies == 100
    with pytest.raises(InvalidRequestError):
        save_collection(ctx, "First Flight", text)
    with pytest.raises(EmptyCollectionError):
        save_collection(ctx, "Empty", "# nothing\n")
    assert [c.name for c in list_collections(ctx)] == ["First Flight"]
    assert list_collections(ctx)[0].content is None                 # listings omit content
    assert rename_collection(ctx, stored.id, "FF").name == "FF"
    assert replace_collection(ctx, stored.id, "1 Sol Ring\n").copies == 1
    delete_collection(ctx, stored.id)
    with pytest.raises(CollectionNotFoundError):
        get_collection(ctx, stored.id)


def test_build_from_stored_collection(ctx):
    text = (SAMPLE / "precons" / "first-flight.txt").read_text()
    stored = save_collection(ctx, "First Flight", text)
    result = build_deck(ctx, BuildRequest(commander="Fixture Flight Commander", collection_id=stored.id))
    assert result.match.source == f"collection:#{stored.id} First Flight"
    rec = save_build(ctx, result)
    assert list_decks(ctx)[0].collection_source == f"collection:#{stored.id} First Flight"
    assert rec.build["request"]["collection_id"] == stored.id


def test_database_cache_per_path(settings):
    assert database(settings) is database(settings)
