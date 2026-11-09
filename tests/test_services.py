"""Service-layer contract tests (run against the bundled offline catalog)."""

from pathlib import Path

import pytest

from commanderai import catalog as catalog_mod
from commanderai.errors import (
    CardNotFoundError,
    CatalogNotFoundError,
    CollectionNotFoundError,
    CollectionTooSmallError,
    CommanderAIError,
    EmptyCollectionError,
    IllegalCommanderError,
    IllegalPartnerError,
    InvalidRequestError,
    NoMatchingCommanderError,
    UnknownColorsError,
    UnknownThemeError,
)
from commanderai.models import DeckSlot
from commanderai.reporting import CollectingReporter, Level
from commanderai.services.analysis import deck_tokens, validate_deck_list
from commanderai.services.build import BuildRequest, build_deck
from commanderai.services.collection import convert_collection, load_collection
from commanderai.services.commanders import list_commanders, suggest_commanders
from commanderai.services.context import ServiceContext
from commanderai.services.reference import vocabulary
from commanderai.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
OFFLINE = ROOT / "tests/fixtures/integration/catalog"
SAMPLE = ROOT / "tests/fixtures/integration/collections"
EXPANDED = SAMPLE / "expanded-collection.txt"
FIRST_FLIGHT = SAMPLE / "precons" / "first-flight.txt"

@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        decks_dir=tmp_path / "decks",
        default_collection=EXPANDED,
        cache_dir=OFFLINE,
        db_path=tmp_path / "test.db",
        offline=True,
    )


@pytest.fixture
def ctx(settings) -> ServiceContext:
    return ServiceContext(settings=settings, reporter=CollectingReporter())


def codes(ctx: ServiceContext) -> list[str]:
    return [n.code for n in ctx.reporter.notices]


# --- settings / catalog ---------------------------------------------------------

def test_settings_from_env_mapping(tmp_path):
    s = Settings.from_env({
        "COMMANDERAI_DECKS_DIR": "d", "COMMANDERAI_COLLECTION": "c.txt",
        "COMMANDERAI_CACHE": "cache", "COMMANDERAI_DB": "x.db", "ANTHROPIC_API_KEY": "k",
    })
    assert s.decks_dir == Path("d")
    assert s.oracle_cards_path == Path("cache") / "oracle_cards.json"
    assert s.db_path == Path("x.db")
    assert s.has_llm_key


def test_catalog_is_cached_and_reported(ctx):
    catalog_mod.clear_cache()
    first = ctx.catalog()
    assert len(first.all_cards) == 291
    assert codes(ctx) == ["catalog.loaded"]
    assert ctx.reporter.steps == ["Loading card database..."]
    # A second context reuses the parsed index.
    other = ServiceContext(settings=ctx.settings, reporter=CollectingReporter())
    assert other.catalog() is first


def test_missing_catalog_raises_typed_error(tmp_path, settings):
    bad = ServiceContext(settings=settings.with_overrides(cache_dir=tmp_path / "nope"))
    with pytest.raises(CatalogNotFoundError):
        bad.catalog()


# --- collection -----------------------------------------------------------------

def test_load_collection_report(ctx):
    loaded = load_collection(ctx, EXPANDED)
    assert loaded.report.unique_cards == 291
    assert loaded.report.copies == 466
    assert loaded.report.unmatched == []


def test_load_collection_from_text(ctx):
    loaded = load_collection(ctx, "1 Sol Ring\n2 Arcane Signet\n1 Definitely Not A Card Name")
    assert loaded.source == "<text>"
    assert {c.name for c in loaded.cards} == {"Sol Ring", "Arcane Signet"}
    assert loaded.report.unmatched == ["Definitely Not A Card Name"]


def test_missing_collection_file(ctx, tmp_path):
    with pytest.raises(CollectionNotFoundError) as exc:
        load_collection(ctx, tmp_path / "missing.txt")
    assert exc.value.status_code == 404
    assert exc.value.data["kind"] == "collection"


def test_convert_collection_csv():
    result = convert_collection(SAMPLE / "expanded-collection.csv")
    assert result.unique_cards == 291 and result.total_cards == 466
    with pytest.raises(EmptyCollectionError):
        convert_collection("")


# --- commanders -----------------------------------------------------------------

def test_list_commanders_sorted_by_rank(ctx):
    commanders = list_commanders(ctx, EXPANDED)
    assert len(commanders) == 16
    ranks = [c.edhrec_rank for c in commanders]
    assert ranks == sorted(ranks)
    assert list_commanders(ctx, EXPANDED, colors="BR")[0].colors in {"B", "R", "BR"}


def test_suggest_commanders_theme(ctx):
    result = suggest_commanders(ctx, EXPANDED, theme="tokens", top=3)
    assert result.theme == "tokens"
    assert result.suggestions[0].commander.name == "Zaxara, the Exemplary"


def test_suggest_commanders_seed_reported(ctx):
    result = suggest_commanders(ctx, EXPANDED, seed=11, top=4)
    assert result.seed == 11 and result.variety == 0.5
    assert "variety.seed" in codes(ctx)


# --- build ----------------------------------------------------------------------

def test_build_deck_structured_result(ctx):
    result = build_deck(ctx, BuildRequest(commander="Zaxara, the Exemplary"))
    deck = result.deck
    assert deck.size == 100
    assert result.validation_errors == []
    assert result.seed is None and result.variety == 0.0
    assert result.match.unique_cards == 291
    assert sum(1 for p in deck.cards if p.slot == DeckSlot.LAND) == 37
    assert codes(ctx) == [
        "catalog.loaded", "collection.matched", "commander.selected",
        "candidates.found", "picks.heuristic",
    ]
    # Result (including notices) must be JSON-serializable for the API.
    assert '"commander.selected"' in result.model_dump_json()


def test_build_is_deterministic(settings):
    a = build_deck(ServiceContext(settings=settings), BuildRequest(commander="Fixture Dragon Commander"))
    b = build_deck(ServiceContext(settings=settings), BuildRequest(commander="Fixture Dragon Commander"))
    assert [p.card.name for p in a.deck.cards] == [p.card.name for p in b.deck.cards]


def test_build_seed_reproducible(settings):
    req = BuildRequest(commander="Fixture Chaos Commander", variety=0.8, seed=42)
    a = build_deck(ServiceContext(settings=settings), req)
    b = build_deck(ServiceContext(settings=settings), req)
    assert a.seed == 42
    assert [p.card.name for p in a.deck.cards] == [p.card.name for p in b.deck.cards]


def test_build_autopick_theme(ctx):
    result = build_deck(ctx, BuildRequest(theme="dragons"))
    assert result.autopick.commander_auto
    assert result.theme == "dragon"
    assert result.quota_changes["THREAT"] == (20, 28)
    assert result.deck.commander.name == "Fixture Dragon Commander"


def test_build_budget_report(ctx):
    result = build_deck(ctx, BuildRequest(commander="Fixture Dragon Commander", budget=40))
    assert result.budget is not None
    assert result.budget.met and result.budget.final_price <= 40
    assert result.budget.swaps > 0


def test_build_collection_text(settings):
    text = FIRST_FLIGHT.read_text()
    result = build_deck(ServiceContext(settings=settings),
                        BuildRequest(commander="Fixture Flight Commander", collection_text=text))
    assert result.match.source == "<text>"
    assert result.deck.size == 100


@pytest.mark.parametrize("req, error", [
    (BuildRequest(), InvalidRequestError),
    (BuildRequest(theme="nonsense"), UnknownThemeError),
    (BuildRequest(colors="purple"), UnknownColorsError),
    (BuildRequest(partner="Muldrotha, the Gravetide", theme="tokens"), InvalidRequestError),
    (BuildRequest(commander="Not A Real Card"), CardNotFoundError),
    (BuildRequest(commander="Sol Ring"), IllegalCommanderError),
    (BuildRequest(commander="Zaxara, the Exemplary", partner="Muldrotha, the Gravetide"), IllegalPartnerError),
    (BuildRequest(colors="colorless", theme="dragons"), NoMatchingCommanderError),
    (BuildRequest(commander="Zaxara, the Exemplary", collection=ROOT / "tests/fixtures/tiny_collection.txt"), CollectionTooSmallError),
])
def test_build_errors_are_typed(ctx, req, error):
    with pytest.raises(error) as exc:
        build_deck(ctx, req)
    assert isinstance(exc.value, CommanderAIError)
    assert exc.value.to_dict()["code"] == error.code


def test_build_request_validation():
    with pytest.raises(ValueError):
        BuildRequest(commander="X", variety=2.0)
    with pytest.raises(ValueError):
        BuildRequest(commander="X", bracket=9)


def test_llm_failure_falls_back_to_heuristic(ctx):
    result = build_deck(ctx, BuildRequest(commander="Zaxara, the Exemplary", use_llm=True))
    assert not result.llm_used
    assert result.llm_error
    assert result.deck.size == 100
    assert any(n.code == "llm.failed" and n.level == Level.WARNING for n in ctx.reporter.notices)


# --- analysis / reference -------------------------------------------------------------

def test_validate_deck_list(ctx):
    result = validate_deck_list(ctx, SAMPLE / "supplied-zaxara-decklist.txt", "Zaxara, the Exemplary")
    assert result.commander == "Zaxara, the Exemplary"
    assert isinstance(result.errors, list)


def test_deck_tokens(ctx):
    result = deck_tokens(ctx, SAMPLE / "precons" / "token-triumph.txt")
    assert result.tokens
    assert all(t.created_by for t in result.tokens)


def test_vocabulary():
    vocab = vocabulary()
    assert any(t.name == "spellslinger" and t.quota_deltas for t in vocab.archetypes)
    assert {g.group for g in vocab.colors} >= {"Mono", "Guilds (2)"}
    assert vocab.brackets[3].startswith("Upgraded")
