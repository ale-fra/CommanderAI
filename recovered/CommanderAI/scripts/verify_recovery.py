#!/usr/bin/env python3
"""Exercise the recovered UI/API using available local data and a temporary DB."""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from commanderai.api import create_app
from commanderai.settings import PROJECT_DIR, Settings


def main() -> None:
    settings = Settings.from_env()
    # Relative .env paths should work regardless of the caller's directory.
    settings = settings.with_overrides(
        default_collection=PROJECT_DIR / settings.default_collection,
        cache_dir=PROJECT_DIR / settings.cache_dir,
        offline=True,
        anthropic_api_key="",
    )
    with tempfile.TemporaryDirectory(prefix="commanderai-recovery-") as directory:
        temp = Path(directory)
        settings = settings.with_overrides(decks_dir=temp / "decks", db_path=temp / "test.db")
        with TestClient(create_app(settings)) as client:
            response = client.get("/")
            assert response.status_code == 200, response.text
            assert '<div id="root">' in response.text
            print("PASS: built React UI is served")

            status = client.get("/api/status")
            assert status.status_code == 200, status.text
            assert status.json()["catalog"]["cards"] > 0

            collections = client.get("/api/collections")
            assert collections.status_code == 200, collections.text
            collection = next(item for item in collections.json() if item["id"] == "default")
            cards = client.get(f"/api/collections/{collection['id']}/cards")
            assert cards.status_code == 200 and len(cards.json()) >= 100, cards.text
            print(f"PASS: collection loaded ({len(cards.json())} unique cards)")

            params = {
                "collection": collection["id"],
                "commander": "Zaxara, the Exemplary",
                "seed": 42,
            }
            response = client.post("/api/builds", json=params)
            assert response.status_code == 200, response.text
            preview = response.json()
            assert preview["result"]["stats"]["card_count"] == 100
            assert preview["result"]["report"]["validation_errors"] == []
            repeated = client.post("/api/builds", json=preview["result"]["params"])
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["result"]["deck"] == preview["result"]["deck"]
            print("PASS: legal 100-card build and reproducible seed")

            saved = client.post("/api/decks", json={"build_id": preview["build_id"], "name": "Recovery check"})
            assert saved.status_code == 201, saved.text
            deck_id = saved.json()["id"]
            detail = client.get(f"/api/decks/{deck_id}")
            assert detail.status_code == 200 and detail.json()["name"] == "Recovery check"
            exported = client.get(f"/api/decks/{deck_id}/export", params={"format": "json"})
            assert exported.status_code == 200, exported.text
            assert exported.headers["content-type"].startswith("application/json")
            assert "Zaxara, the Exemplary" in exported.text
            assert client.delete(f"/api/decks/{deck_id}").status_code == 204
            assert client.get(f"/api/decks/{deck_id}").status_code == 404
            print("PASS: SQLite save/read, JSON export and delete")


if __name__ == "__main__":
    main()
