"""Regression tests for the phase-D bug fixes (D1-D5, see tests/golden/CHANGES.md)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from commanderai.data.card_index import CardIndex
from commanderai.data.scryfall import load_cards
from commanderai.deckbuilder.bracket import (
    SPELLBOOK_BASE,
    check_bracket,
    check_bracket_offline,
    is_extra_turn_card,
    is_mass_land_denial_card,
)
from commanderai.deckbuilder.budget import enforce_budget
from commanderai.deckbuilder.tokens import COPY_TOKEN_NAME, extract_tokens
from commanderai.errors import InsufficientCardsError
from commanderai.models import Card, Deck, DeckPick, DeckSlot
from commanderai.reporting import CollectingReporter
from commanderai.services.analysis import validate_deck_list
from commanderai.services.build import BuildRequest, build_deck
from commanderai.services.context import ServiceContext
from commanderai.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
OFFLINE = ROOT / "offline-data"
SAMPLE = ROOT / "commanderai-sample"
PRECONS = SAMPLE / "precons"

needs_catalog = pytest.mark.skipif(
    not (OFFLINE / "oracle_cards.json").exists(), reason="offline catalog not available"
)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        decks_dir=tmp_path / "decks", default_collection=SAMPLE / "expanded-collection.txt",
        cache_dir=OFFLINE, db_path=tmp_path / "lib.db",
    )


def ctx_for(settings, **overrides) -> ServiceContext:
    return ServiceContext(settings=settings.with_overrides(**overrides) if overrides else settings,
                          reporter=CollectingReporter())


def card(name, text="", price=None, type_line="Instant", colors=("U",), rank=None, gc=False, **kw):
    prices = {"usd": price} if price is not None else {}
    return Card(name=name, oracle_text=text, type_line=type_line, color_identity=list(colors),
                prices=prices, edhrec_rank=rank, game_changer=gc, **kw)


# ---------------------------------------------------------------------------
# D1 — validate counts quantities, checks commander / partner
# ---------------------------------------------------------------------------

@needs_catalog
@pytest.mark.parametrize("precon, commander", [
    ("first-flight", "Isperia, Supreme Judge"),
    ("grave-danger", "Gisa and Geralf"),
    ("chaos-incarnate", "Kardur, Doomscourge"),
    ("draconic-destruction", "Atarka, World Render"),
    ("token-triumph", "Emmara, Soul of the Accord"),
])
def test_d1_every_precon_is_valid(settings, precon, commander):
    result = validate_deck_list(ctx_for(settings), PRECONS / f"{precon}.txt", commander)
    assert result.errors == []
    assert result.card_count == 100


@needs_catalog
def test_d1_quantities_and_singleton(settings):
    ok = "1 Isperia, Supreme Judge\n1 Sol Ring\n98 Island\n"
    assert validate_deck_list(ctx_for(settings), ok, "Isperia, Supreme Judge").errors == []
    dup = "1 Isperia, Supreme Judge\n2 Sol Ring\n97 Island\n"
    errors = validate_deck_list(ctx_for(settings), dup, "Isperia, Supreme Judge").errors
    assert errors == ["Duplicate: Sol Ring appears 2 times"]


@needs_catalog
def test_d1_commander_need_not_be_listed(settings):
    result = validate_deck_list(ctx_for(settings), "1 Sol Ring\n98 Island\n", "Isperia, Supreme Judge")
    assert result.errors == [] and result.card_count == 100


@needs_catalog
def test_d1_unknown_cards_reported(settings):
    result = validate_deck_list(ctx_for(settings), "1 Sol Ring\n1 Not A Card\n", "Isperia, Supreme Judge")
    assert result.unknown_cards == ["Not A Card"]
    assert result.card_count == 2


@needs_catalog
def test_d1_illegal_commander_and_partner(settings):
    errors = validate_deck_list(ctx_for(settings), "98 Island\n", "Sol Ring").errors
    assert "Sol Ring can't be a commander" in errors
    errors = validate_deck_list(
        ctx_for(settings), "97 Island\n", "Isperia, Supreme Judge", "Gisa and Geralf"
    ).errors
    assert "Isperia, Supreme Judge and Gisa and Geralf can't be partners" in errors


def test_d1_partner_deck_counts_both_commanders(settings):
    a = card("Alpha", "Partner", type_line="Legendary Creature — Human", colors=("W",), keywords=["Partner"])
    b = card("Beta", "Partner", type_line="Legendary Creature — Elf", colors=("G",), keywords=["Partner"])
    plains = card("Plains", type_line="Basic Land — Plains", colors=())
    index = CardIndex([a, b, plains])
    ctx = ServiceContext(settings=settings, reporter=CollectingReporter(),
                         catalog_loader=lambda s: index)
    result = validate_deck_list(ctx, "1 Alpha\n1 Beta\n98 Plains\n", "Alpha", "Beta")
    assert result.errors == [] and result.card_count == 100 and result.partner == "Beta"


# ---------------------------------------------------------------------------
# D2 — one price rule, commanders included
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prices, expected", [
    ({"usd": "1.50"}, 1.5),
    ({"usd": None, "usd_foil": "4.00"}, 4.0),
    ({"usd": None, "usd_foil": None, "usd_etched": "9.99"}, 9.99),
    ({"usd": "n/a", "usd_foil": "2.00"}, 2.0),
    ({}, None),
])
def test_d2_price_usd(prices, expected):
    assert Card(name="X", prices=prices).price_usd == expected


def test_d2_total_price_includes_commanders_and_foil():
    cmdr = card("Cmdr", price="5.00", type_line="Legendary Creature")
    foil_only = Card(name="Foil", prices={"usd_foil": "3.00"})
    unpriced = card("Mystery")
    basic = Card(name="Forest", type_line="Basic Land")
    deck = Deck(commander=cmdr, cards=[
        DeckPick(card=foil_only, slot=DeckSlot.DRAW),
        DeckPick(card=unpriced, slot=DeckSlot.DRAW),
        DeckPick(card=basic, slot=DeckSlot.LAND),
    ])
    assert deck.total_price == 8.0
    assert deck.unpriced_cards == 1          # basics are not counted as "unpriced"


def test_d2_enforce_budget_counts_the_commander():
    cmdr = card("Cmdr", price="8.00", type_line="Legendary Creature")
    pricey = card("Pricey", price="5.00", type_line="Creature")
    cheap = card("Cheap", price="1.00", type_line="Creature")
    picks = [DeckPick(card=pricey, slot=DeckSlot.THREAT)]
    from commanderai.models import ScoredCard
    candidates = {DeckSlot.THREAT: [ScoredCard(card=pricey, score=1, slot=DeckSlot.THREAT),
                                    ScoredCard(card=cheap, score=1, slot=DeckSlot.THREAT)]}
    # 8 + 5 = 13 > 10 → must swap to the $1 card (8 + 1 = 9).
    new, swaps, final = enforce_budget(picks, candidates, cmdr, budget=10)
    assert swaps == 1 and new[0].card.name == "Cheap" and final == 9.0


@needs_catalog
def test_d2_build_budget_matches_deck_price(settings):
    result = build_deck(ctx_for(settings), BuildRequest(commander="Atarka, World Render", budget=40))
    report = result.budget
    assert report.commanders_price == 0.39
    assert round(report.final_price, 2) == round(result.deck.total_price, 2)
    assert report.met and result.deck.total_price <= 40


@needs_catalog
def test_d2_commanders_over_budget_warn(settings):
    ctx = ctx_for(settings)
    with pytest.raises(InsufficientCardsError):
        build_deck(ctx, BuildRequest(commander="Gargos, Vicious Watcher", budget=1))
    assert any(n.code == "budget.commanders_exceed" for n in ctx.reporter.notices)


# ---------------------------------------------------------------------------
# D3 — offline bracket rules (+ partner sent online, forced offline mode)
# ---------------------------------------------------------------------------

GC = [card(f"GC{i}", gc=True, rank=r) for i, r in enumerate([50, 10, 30, 20])]
EXTRA = card("Time Warp", "Target player takes an extra turn after this one.")
MLD = card("Armageddon", "Destroy all lands.", colors=("W",))
PLAIN = card("Opt", "Scry 1. Draw a card.")
POOL = GC + [EXTRA, MLD, PLAIN]


@pytest.mark.parametrize("bracket, excluded, prioritized", [
    (1, {"GC0", "GC1", "GC2", "GC3", "Time Warp", "Armageddon"}, set()),
    (2, {"GC0", "GC1", "GC2", "GC3", "Time Warp", "Armageddon"}, set()),
    (3, {"GC0", "Time Warp", "Armageddon"}, {"GC1", "GC3", "GC2"}),   # best 3 by EDHREC rank kept
    (4, set(), set()),
])
def test_d3_offline_rules(bracket, excluded, prioritized):
    result = check_bracket_offline(POOL, bracket, reason="test")
    assert {n for n, _ in result.excluded_cards} == excluded
    assert result.prioritized_names == prioritized
    assert result.allowed_names == {c.name for c in POOL} - excluded
    assert result.mode == "offline" and result.offline_reason == "test"


def test_d3_detectors():
    assert is_extra_turn_card(EXTRA) and not is_extra_turn_card(PLAIN)
    assert not is_extra_turn_card(card("Ugin's Nexus", "If a player would begin an extra turn, that player skips that turn instead."))
    assert is_mass_land_denial_card(MLD)
    assert not is_mass_land_denial_card(card("Wrath", "Destroy all creatures."))


def test_d3_bracket5_skips_everything():
    result = check_bracket(PLAIN, POOL, 5)
    assert result.mode == "skipped" and result.allowed_names == {c.name for c in POOL}


@respx.mock(assert_all_called=False)
def test_d3_forced_offline_makes_no_request(respx_mock):
    route = respx_mock.post(f"{SPELLBOOK_BASE}/estimate-bracket")
    result = check_bracket(PLAIN, POOL, 2, offline=True)
    assert not route.called
    assert result.mode == "offline"


@respx.mock
def test_d3_network_error_falls_back(respx_mock):
    respx_mock.post(f"{SPELLBOOK_BASE}/estimate-bracket").mock(side_effect=httpx.ConnectError("down"))
    result = check_bracket(PLAIN, POOL, 2)
    assert result.mode == "offline" and "unreachable" in result.offline_reason
    assert "GC1" not in result.allowed_names


@respx.mock
def test_d3_online_sends_partner_and_uses_api_result(respx_mock):
    route = respx_mock.post(f"{SPELLBOOK_BASE}/estimate-bracket").mock(
        return_value=httpx.Response(200, json={
            "cards": [{"card": {"name": "GC1"}, "gameChanger": True}],
            "combos": [],
        })
    )
    partner = card("Partner B", type_line="Legendary Creature")
    result = check_bracket(PLAIN, POOL, 2, partner=partner)
    payload = json.loads(route.calls[0].request.content)
    assert [c["card"] for c in payload["commanders"]] == ["Opt", "Partner B"]
    assert result.mode == "online"
    assert [n for n, _ in result.excluded_cards] == ["GC1"]      # API decides, not local flags


@needs_catalog
def test_d3_build_reports_offline_bracket(settings):
    ctx = ctx_for(settings, offline=True)
    result = build_deck(ctx, BuildRequest(commander="Zaxara, the Exemplary", bracket=2))
    assert result.bracket.mode == "offline"
    assert {c.name for c in result.bracket.excluded_cards} == {"Rhystic Study", "Mystical Tutor"}
    assert not {p.card.name for p in result.deck.cards} & {"Rhystic Study", "Mystical Tutor"}
    assert any(n.code == "bracket.offline" for n in ctx.reporter.notices)


@needs_catalog
def test_d3_offline_mode_blocks_llm_even_with_key(settings):
    ctx = ctx_for(settings, offline=True, anthropic_api_key="sk-test")
    result = build_deck(ctx, BuildRequest(commander="Zaxara, the Exemplary", use_llm=True))
    assert not result.llm_used and "offline mode" in result.llm_error


def test_d3_offline_setting_from_env():
    base = {"COMMANDERAI_CACHE": "c"}
    assert Settings.from_env({**base, "COMMANDERAI_OFFLINE": "1"}).offline
    assert Settings.from_env({**base, "COMMANDERAI_OFFLINE": "true"}).offline
    assert not Settings.from_env(base).offline


# ---------------------------------------------------------------------------
# D5 — token output
# ---------------------------------------------------------------------------

def _tokens(*texts):
    return extract_tokens([card(f"C{i}", t) for i, t in enumerate(texts)])


def test_d5_predefined_artifact_tokens_have_a_type():
    (food,) = _tokens("When this enters, create a Food token.")
    assert (food.name, food.types) == ("Food", "Artifact")


def test_d5_tapped_is_not_part_of_the_name():
    tokens = _tokens("Create a tapped 2/2 black Zombie creature token.",
                     "Create a 2/2 black Zombie creature token.")
    assert len(tokens) == 1
    assert (tokens[0].name, tokens[0].power, tokens[0].created_by) == ("Zombie", "2", ["C0", "C1"])


def test_d5_copy_tokens():
    tokens = _tokens("Create a token that's a copy of that creature.",
                     "Create a token that's a copy of a creature token you control.")
    assert [t.name for t in tokens] == [COPY_TOKEN_NAME]
    assert tokens[0].created_by == ["C0", "C1"]


@needs_catalog
def test_d5_no_malformed_token_names_in_catalog():
    tokens = extract_tokens(load_cards(OFFLINE / "oracle_cards.json"))
    for t in tokens:
        assert not t.name.lower().startswith(("token", "tapped")), t.name
        assert t.types or t.power or t.name == COPY_TOKEN_NAME, t.name
