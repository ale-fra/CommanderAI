"""API integration tests using the small demo catalog shipped with the project."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commanderai.api import create_app
from commanderai.settings import Settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        default_collection=ROOT / "data/collezione-fittizia.csv",
        cache_dir=ROOT / "data/demo-catalog",
        decks_dir=tmp_path / "decks",
        db_path=tmp_path / "library.db",
        offline=True,
    )
    with TestClient(create_app(settings, web_dist=None, sample_dir=tmp_path / "samples")) as c:
        yield c


def test_demo_collection_and_commander_data(client):
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["default_collection"] == "default"
    cards = client.get("/api/collections/default/cards")
    assert cards.status_code == 200
    assert len(cards.json()) == 194
    assert any(card["name"] == "Zaxara, the Exemplary" for card in cards.json())
    card = client.get("/api/card", params={"name": "Zaxara, the Exemplary"})
    assert card.status_code == 200 and card.json()["is_commander"]


def test_uploaded_collection_can_be_replaced_and_deleted(client):
    created = client.post("/api/collections", json={"name": "Demo", "content": "1 Sol Ring"})
    assert created.status_code == 201
    collection_id = created.json()["id"]
    updated = client.patch(
        f"/api/collections/{collection_id}", json={"content": "1 Sol Ring\n2 Forest"}
    )
    assert updated.status_code == 200
    cards = client.get(f"/api/collections/{collection_id}/cards").json()
    assert {card["name"]: card["quantity"] for card in cards} == {"Sol Ring": 1, "Forest": 2}
    assert client.delete(f"/api/collections/{collection_id}").status_code == 204
    assert client.get(f"/api/collections/{collection_id}").status_code == 404


def test_build_reproduce_save_export_and_delete(client):
    params = {"collection": "default", "commander": "Zaxara, the Exemplary", "seed": 42}
    response = client.post("/api/builds", json=params)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["result"]["stats"]["card_count"] == 100
    assert preview["result"]["report"]["validation_errors"] == []
    repeated = client.post("/api/builds", json=preview["result"]["params"])
    assert repeated.status_code == 200
    assert repeated.json()["result"]["deck"] == preview["result"]["deck"]
    saved = client.post("/api/decks", json={"build_id": preview["build_id"], "name": "Demo deck"})
    assert saved.status_code == 201
    deck_id = saved.json()["id"]
    assert client.get(f"/api/decks/{deck_id}").json()["name"] == "Demo deck"
    export = client.get(f"/api/decks/{deck_id}/export", params={"format": "json"})
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/json")
    assert "Zaxara, the Exemplary" in export.text
    assert client.delete(f"/api/decks/{deck_id}").status_code == 204
    assert client.get(f"/api/decks/{deck_id}").status_code == 404
