"""HTTP API contract tests (FastAPI TestClient, offline catalog). See docs/UI_PLAN.md §2."""

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="the 'web' extra is not installed")

from fastapi.testclient import TestClient

from commanderai.api import create_app
from commanderai.api.openapi import schema
from commanderai.services.build import BuildRequest, build_deck
from commanderai.services.context import ServiceContext
from commanderai.services.deck_files import render_deck
from commanderai.services.library import save_build
from commanderai.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "commanderai-sample"
EXPANDED = "builtin:expanded"


def make_settings(tmp_path) -> Settings:
    return Settings(
        decks_dir=tmp_path / "decks",
        default_collection=SAMPLE / "expanded-collection.txt",
        cache_dir=ROOT / "offline-data",
        db_path=tmp_path / "api.db",
        offline=True,
    )


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    if not settings.oracle_cards_path.exists() or not settings.default_collection.exists():
        pytest.skip("optional full-catalog API fixtures are not installed; see docs/TESTING.md")
    with TestClient(create_app(settings, web_dist=None)) as c:   # runs the startup hook
        yield c


def error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code, body
    assert set(body) == {"code", "message", "details", "data"}
    return body


def build(client, **params) -> dict:
    r = client.post("/api/builds", json={"collection": EXPANDED, **params})
    assert r.status_code == 200, r.text
    return r.json()


# --- system -------------------------------------------------------------------------

def test_status(client):
    body = client.get("/api/status").json()
    assert body["catalog"] == {"cards": 500, "snapshot": "2026-11-04T22:02:02.236+00:00"}
    assert body["offline"] is True
    assert body["database"] == {"decks": 0, "collections": 0}
    assert body["default_collection"] == EXPANDED
    assert body["migration"] == {"imported": 0, "failed": 0}


@pytest.mark.skipif(
    not (ROOT / "tests/golden/baseline/build-zaxara/decks/zaxara__the_exemplary.txt").exists(),
    reason="optional golden deck fixture is not installed",
)
def test_startup_migrates_legacy_txt_decks(tmp_path):
    settings = make_settings(tmp_path)
    settings.decks_dir.mkdir(parents=True)
    legacy = ROOT / "tests/golden/baseline/build-zaxara/decks/zaxara__the_exemplary.txt"
    (settings.decks_dir / "old.txt").write_text(legacy.read_text())
    (settings.decks_dir / "junk.txt").write_text("not a deck\n")
    with TestClient(create_app(settings, web_dist=None)) as c:
        status = c.get("/api/status").json()
        assert status["migration"] == {"imported": 1, "failed": 1}
        assert status["database"]["decks"] == 1
        deck = c.get("/api/decks/1").json()
        assert deck["source"] == "legacy" and deck["report"] is None and deck["params"] is None
        assert deck["stats"]["card_count"] == 100


def test_vocabulary(client):
    body = client.get("/api/vocabulary").json()
    assert {"colors", "archetypes", "tribes", "aliases", "formats", "brackets"} <= set(body)
    assert any(a["name"] == "tokens" for a in body["archetypes"])
    assert body["brackets"]["2"].startswith("Core")


# --- cards ----------------------------------------------------------------------------

def test_card_detail_double_faced(client):
    r = client.get("/api/card", params={"name": "Invasion of Zendikar // Awakened Skyclave"})
    body = r.json()
    assert r.status_code == 200
    assert body["images"]["front"].endswith("-front.jpg") and body["images"]["back"].endswith("-back.jpg")
    assert [f["name"] for f in body["faces"]] == ["Invasion of Zendikar", "Awakened Skyclave"]
    assert body["rarity"] == "uncommon" and body["set_name"]


def test_card_summary_fields(client):
    body = client.get("/api/card", params={"name": "Rhystic Study"}).json()
    assert body["role"] == "DRAW" and body["game_changer"] is True and body["is_commander"] is False
    assert isinstance(body["price_usd"], float)
    assert client.get("/api/card", params={"name": "Sol Ring"}).json()["price_usd"] is None
    assert client.get("/api/card", params={"name": "Zaxara, the Exemplary"}).json()["is_commander"]


def test_card_errors(client):
    error(client.get("/api/card", params={"name": "Nope"}), 404, "card_not_found")
    error(client.get("/api/card"), 422, "validation_error")


def test_images_are_served_with_long_cache(client):
    url = client.get("/api/card", params={"name": "Sol Ring"}).json()["images"]["front"]
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert "immutable" in r.headers["cache-control"]


# --- collections ------------------------------------------------------------------------

def test_collection_list(client):
    items = client.get("/api/collections").json()
    ids = [c["id"] for c in items]
    assert ids[:2] == [EXPANDED, "builtin:sample"]
    assert {f"builtin:precon:{p}" for p in
            ("first-flight", "grave-danger", "chaos-incarnate", "draconic-destruction", "token-triumph")} <= set(ids)
    expanded = items[0]
    assert expanded == {
        "id": EXPANDED, "kind": "builtin", "name": "Expanded sample",
        "description": "Sample collection plus the five Starter Commander Decks",
        "entries": 500, "copies": 796, "editable": False,
    }
    ff = next(c for c in items if c["id"] == "builtin:precon:first-flight")
    assert ff["name"] == "Precon: First Flight" and ff["copies"] == 100


def test_collection_detail_and_cards(client):
    detail = client.get(f"/api/collections/{EXPANDED}").json()
    assert detail["unique_cards"] == 500 and detail["commanders"] == 27
    assert detail["match"]["unmatched"] == []
    cards = client.get(f"/api/collections/{EXPANDED}/cards").json()
    assert len(cards) == 500
    by_name = {c["name"]: c for c in cards}
    assert by_name["Sol Ring"]["quantity"] == 6
    assert by_name["Zaxara, the Exemplary"]["images"]["front"]
    assert sum(c["quantity"] for c in cards) == 796


def test_collection_not_found(client):
    error(client.get("/api/collections/builtin:nope"), 404, "collection_not_found")
    error(client.get("/api/collections/stored:999"), 404, "collection_not_found")
    error(client.get("/api/collections/stored:abc"), 404, "collection_not_found")


def test_collection_preview(client):
    r = client.post("/api/collections/preview",
                    json={"content": "1 Sol Ring\n2 Arcane Signat\n1 Not A Real Card\n1 Zaxara, the Exemplary\n"})
    body = r.json()
    assert r.status_code == 200
    assert body["entries"] == 4 and body["copies"] == 5 and body["unique_cards"] == 3 and body["commanders"] == 1
    assert body["match"]["fuzzy"] == [{"original": "Arcane Signat", "corrected": "Arcane Signet"}]
    assert body["match"]["unmatched"] == ["Not A Real Card"]
    error(client.post("/api/collections/preview", json={"content": "# nothing\n"}), 422, "empty_collection")


def test_stored_collection_lifecycle(client):
    content = (SAMPLE / "precons" / "grave-danger.txt").read_text()
    r = client.post("/api/collections", json={"name": "My zombies", "content": content})
    assert r.status_code == 201
    created = r.json()
    assert created["id"] == "stored:1" and created["editable"] and created["copies"] == 100
    assert created["commanders"] == 3
    assert client.get("/api/collections").json()[-1]["id"] == "stored:1"
    error(client.post("/api/collections", json={"name": "My zombies", "content": content}), 400, "invalid_request")

    patched = client.patch("/api/collections/stored:1", json={"name": "Zombies!", "content": "1 Sol Ring\n"}).json()
    assert patched["name"] == "Zombies!" and patched["copies"] == 1
    assert client.get("/api/status").json()["database"]["collections"] == 1

    assert client.delete("/api/collections/stored:1").status_code == 204
    error(client.get("/api/collections/stored:1"), 404, "collection_not_found")


def test_builtin_collections_are_read_only(client):
    error(client.patch(f"/api/collections/{EXPANDED}", json={"name": "x"}), 409, "read_only")
    error(client.delete(f"/api/collections/{EXPANDED}"), 409, "read_only")


def test_upload_validation(client):
    error(client.post("/api/collections", json={"name": "", "content": "1 Sol Ring"}), 422, "validation_error")


# --- commanders ---------------------------------------------------------------------------

def test_commanders(client):
    items = client.get("/api/commanders", params={"collection": EXPANDED}).json()
    assert len(items) == 27
    assert items[0]["card"]["name"] == "Syr Konrad, the Grim"
    zaxara = next(c for c in items if c["card"]["name"] == "Zaxara, the Exemplary")
    assert zaxara["colors"] == "UBG" and zaxara["support"] == 334 and zaxara["can_take_partner"] is False
    simic = client.get("/api/commanders", params={"collection": EXPANDED, "colors": "simic"}).json()
    assert {c["colors"] for c in simic} <= {"U", "G", "UG", "C"}
    error(client.get("/api/commanders", params={"collection": EXPANDED, "colors": "purple"}), 400, "unknown_colors")


def test_commander_suggestions(client):
    body = client.get("/api/commanders/suggestions",
                      params={"collection": EXPANDED, "theme": "tokens", "top": 3}).json()
    assert body["theme"] == "tokens" and len(body["suggestions"]) == 3
    assert body["suggestions"][0]["commander"]["card"]["name"] == "Zaxara, the Exemplary"
    seeded = client.get("/api/commanders/suggestions",
                        params={"collection": EXPANDED, "seed": 11, "top": 4}).json()
    assert seeded["seed"] == 11 and seeded["variety"] == 0.5
    error(client.get("/api/commanders/suggestions", params={"collection": EXPANDED, "theme": "x"}),
          400, "unknown_theme")
    error(client.get("/api/commanders/suggestions", params={"collection": EXPANDED, "top": 0}),
          422, "validation_error")


def test_partners(client):
    assert client.get("/api/commanders/partners",
                      params={"collection": EXPANDED, "commander": "Zaxara, the Exemplary"}).json() == []
    error(client.get("/api/commanders/partners", params={"collection": EXPANDED, "commander": "Nope"}),
          404, "card_not_found")


# --- builds ---------------------------------------------------------------------------------

def test_build_preview(client):
    body = build(client, commander="Zaxara, the Exemplary")
    assert len(body["build_id"]) == 32 and body["expires_at"]
    result = body["result"]
    deck, stats, report = result["deck"], result["stats"], result["report"]
    assert deck["commander"]["name"] == "Zaxara, the Exemplary" and len(deck["cards"]) == 99
    assert stats["card_count"] == 100 and stats["lands"] == 37
    assert sum(stats["mana_curve"].values()) == 62
    assert stats["roles"]["RAMP"] == 10 and stats["role_targets"]["LAND"] == 37
    assert sum(stats["types"].values()) == 100
    assert set(stats["color_pips"]) == set("WUBRG") and stats["color_pips"]["W"] == 0
    assert any(t["name"] == "Food" for t in result["tokens"])
    assert [n["code"] for n in report["notices"]][:2] == ["catalog.loaded", "collection.matched"]
    assert report["match"]["source"] == "Expanded sample [builtin:expanded]"
    assert result["params"]["seed"] is None


def test_build_is_reproducible_with_returned_seed(client):
    first = build(client, commander="Kardur, Doomscourge", variety=0.8)
    params = first["result"]["params"]
    assert isinstance(params["seed"], int)
    again = client.post("/api/builds", json=params).json()
    names = lambda b: [c["card"]["name"] for c in b["result"]["deck"]["cards"]]
    assert names(again) == names(first)


def test_build_autopick_budget_and_bracket(client):
    report = build(client, theme="dragons", budget=60, bracket=2)["result"]["report"]
    assert report["autopick"]["commander_auto"] is True
    assert report["budget"]["met"] is True and report["budget"]["final_price"] <= 60
    assert report["bracket"]["mode"] == "offline"
    assert report["quota_changes"]["THREAT"] == {"before": 20, "after": 28}


@pytest.mark.parametrize("params, status, code", [
    ({}, 400, "invalid_request"),
    ({"commander": "Nobody"}, 404, "card_not_found"),
    ({"commander": "Sol Ring"}, 422, "illegal_commander"),
    ({"theme": "nonsense"}, 400, "unknown_theme"),
    ({"commander": "Zaxara, the Exemplary", "lands": 150}, 422, "validation_error"),
    ({"collection": "builtin:nope", "commander": "Zaxara, the Exemplary"}, 404, "collection_not_found"),
])
def test_build_errors(client, params, status, code):
    error(client.post("/api/builds", json={"collection": EXPANDED, **params}), status, code)


def test_build_from_stored_collection(client):
    client.post("/api/collections", json={"name": "FF", "content": (SAMPLE / "precons/first-flight.txt").read_text()})
    body = client.post("/api/builds", json={"collection": "stored:1", "commander": "Isperia, Supreme Judge"}).json()
    assert body["result"]["report"]["match"]["source"] == "FF [stored:1]"


# --- decks ------------------------------------------------------------------------------------

def save(client, build_body, name=None) -> dict:
    r = client.post("/api/decks", json={"build_id": build_body["build_id"], "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_save_build_and_read_back(client):
    preview = build(client, commander="Zaxara, the Exemplary", theme="counters", seed=7, variety=0.5)
    deck = save(client, preview, name="My Zaxara")
    assert deck["id"] == 1 and deck["name"] == "My Zaxara" and deck["source"] == "api"
    assert deck["deck"] == preview["result"]["deck"]
    assert deck["stats"] == preview["result"]["stats"]
    assert deck["params"] == preview["result"]["params"]
    assert deck["report"]["theme"] == "counters" and deck["validation_errors"] == []
    assert deck["collection_source"] == "Expanded sample [builtin:expanded]"
    assert client.get("/api/decks/1").json() == deck


def test_save_expired_build(client):
    error(client.post("/api/decks", json={"build_id": "0" * 32}), 410, "gone")


def test_deck_list_filters(client):
    save(client, build(client, commander="Zaxara, the Exemplary"))
    save(client, build(client, commander="Atarka, World Render"), name="Dragons!")
    save(client, build(client, commander="Zaxara, the Exemplary"), name="Hydras")
    body = client.get("/api/decks").json()
    assert body["total"] == 3 and [d["id"] for d in body["items"]] == [3, 2, 1]
    assert body["items"][0]["commander_image"].startswith("/api/images/")
    assert client.get("/api/decks", params={"commander": "Zaxara, the Exemplary"}).json()["total"] == 2
    assert [d["name"] for d in client.get("/api/decks", params={"q": "drag"}).json()["items"]] == ["Dragons!"]
    assert client.get("/api/decks", params={"q": "atarka"}).json()["total"] == 1    # commander name
    assert client.get("/api/decks", params={"q": "100%_"}).json()["total"] == 0     # wildcards are literal
    page = client.get("/api/decks", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3 and [d["id"] for d in page["items"]] == [2]
    assert client.get("/api/decks", params={"source": "api"}).json()["total"] == 3


def test_update_and_delete_deck(client):
    save(client, build(client, commander="Zaxara, the Exemplary"))
    updated = client.patch("/api/decks/1", json={"name": "Renamed", "notes": "Try more ramp"}).json()
    assert updated["name"] == "Renamed" and updated["notes"] == "Try more ramp"
    error(client.patch("/api/decks/1", json={"name": ""}), 422, "validation_error")
    assert client.delete("/api/decks/1").status_code == 204
    error(client.get("/api/decks/1"), 404, "deck_not_found")
    error(client.delete("/api/decks/1"), 404, "deck_not_found")


@pytest.mark.parametrize("fmt, media, first_line", [
    ("text", "text/plain", "=== Commander: Emmara, Soul of the Accord ==="),
    ("mtgo", "text/plain", "1 Emmara, Soul of the Accord"),
    ("moxfield", "text/plain", "1 Emmara, Soul of the Accord *CMDR*"),
    ("archidekt", "text/plain", "1 Emmara, Soul of the Accord [Commander]"),
    ("json", "application/json", "{"),
])
def test_export(client, fmt, media, first_line):
    save(client, build(client, commander="Emmara, Soul of the Accord"), name="Émmara tokens")
    r = client.get("/api/decks/1/export", params={"format": fmt})
    assert r.status_code == 200 and r.headers["content-type"].startswith(media)
    assert r.text.splitlines()[0] == first_line
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=") and f"-{fmt}." in disposition
    assert "filename*=UTF-8''" in disposition


def test_export_errors(client):
    error(client.get("/api/decks/9/export"), 404, "deck_not_found")
    save(client, build(client, commander="Zaxara, the Exemplary"))
    error(client.get("/api/decks/1/export", params={"format": "pdf"}), 422, "validation_error")


def test_json_export_import_roundtrip(client):
    original = save(client, build(client, commander="Atarka, World Render", budget=50))
    exported = client.get("/api/decks/1/export", params={"format": "json"}).text
    r = client.post("/api/decks/import", json={"content": exported, "name": "Copy"})
    assert r.status_code == 201
    body = r.json()
    assert body["unknown_cards"] == [] and body["deck"]["id"] == 2 and body["deck"]["source"] == "import"
    assert body["deck"]["deck"] == original["deck"] and body["deck"]["report"] == original["report"]


def test_text_import(client):
    r = client.post("/api/decks/import", json={
        "content": "1 Isperia, Supreme Judge\n1 Sol Ring\n1 Not A Real Card\n97 Island\n", "filename": "isperia.txt"})
    body = r.json()
    assert r.status_code == 201 and body["unknown_cards"] == ["Not A Real Card"]
    assert body["deck"]["name"] == "isperia" and body["deck"]["stats"]["card_count"] == 99
    assert body["deck"]["validation_errors"] == ["Deck has 98 cards, need exactly 99 (+ 1 commander)"]
    error(client.post("/api/decks/import", json={"content": "hello\n"}), 422, "deck_import_failed")
    error(client.post("/api/decks/import", json={"content": '{"format": "other"}'}), 422, "deck_import_failed")


def test_cli_built_deck_can_be_rebuilt_from_the_ui(client, settings):
    ctx = ServiceContext(settings=settings)
    result = build_deck(ctx, BuildRequest(collection=SAMPLE / "expanded-collection.txt",
                                          commander="Kardur, Doomscourge", seed=3))
    path = settings.decks_dir / "kardur.txt"
    settings.decks_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(render_deck(result.deck))
    save_build(ctx, result, source="cli", export_path=path, export_format="text")
    deck = client.get("/api/decks/1").json()
    assert deck["source"] == "cli"
    assert deck["params"] == {
        "collection": EXPANDED, "commander": "Kardur, Doomscourge", "partner": None, "theme": None,
        "colors": None, "lands": 37, "variety": 0.0, "seed": 3, "budget": None, "bracket": None,
    }
    rebuilt = client.post("/api/builds", json=deck["params"]).json()["result"]["deck"]
    assert rebuilt == deck["deck"]


# --- routing / schema ----------------------------------------------------------------------------

def test_unknown_api_paths(client):
    error(client.get("/api/nope"), 404, "not_found")
    error(client.post("/api/nope"), 404, "not_found")


def test_spa_fallback(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "robots.txt").write_text("ok")
    with TestClient(create_app(make_settings(tmp_path), web_dist=dist)) as c:
        assert c.get("/decks/3").text == "<html>app</html>"            # client route
        assert c.get("/robots.txt").text == "ok"                       # real file
        assert c.get("/../../etc/passwd").text == "<html>app</html>"   # no traversal
        error(c.get("/api/unknown"), 404, "not_found")


def test_openapi_snapshot_is_current():
    """web/openapi.json (source of the generated TypeScript types) must match the code.

    Regenerate with:  cd web && npm run gen:api
    """
    committed = json.loads((ROOT / "web" / "openapi.json").read_text())
    assert committed == schema(), "web/openapi.json is stale — run `cd web && npm run gen:api`"
