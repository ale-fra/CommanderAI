"""Fail clearly if packaged integration data is incomplete or inconsistent."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from commanderai.collection.parser import parse_collection
from commanderai.data.scryfall import load_cards

FIXTURES = Path(__file__).parent / "fixtures/integration"
COLLECTIONS = sorted((FIXTURES / "collections").rglob("*.txt")) + sorted(
    (FIXTURES / "collections").glob("*.csv")
)


def test_fixture_catalog_is_complete():
    cards = load_cards(FIXTURES / "catalog/oracle_cards.json")
    assert len(cards) == len({card.name for card in cards}) == 291
    assert {"Plains", "Island", "Swamp", "Mountain", "Forest"} <= {c.name for c in cards}
    assert len(COLLECTIONS) == 10


@pytest.mark.parametrize("path", COLLECTIONS, ids=lambda p: p.name)
def test_every_collection_name_has_an_exact_catalog_entry(path):
    names = {card.name for card in load_cards(FIXTURES / "catalog/oracle_cards.json")}
    entries = parse_collection(path)
    assert entries
    assert {entry.card_name for entry in entries} <= names
    if path.parent.name == "precons":
        assert len(entries) == 72
        assert sum(entry.quantity for entry in entries) == 100


def test_images_are_bundled_for_every_card_face():
    cache = FIXTURES / "catalog"
    cards = json.loads((cache / "oracle_cards.json").read_text())
    manifest = json.loads((cache / "image-manifest.json").read_text())
    expected = {(c["name"], i) for c in cards
                for i, _ in enumerate(c.get("card_faces") or [c])}
    assert {(entry["name"], entry["face_index"]) for entry in manifest} == expected
    for entry in manifest:
        path = cache / entry["local_path"]
        assert path.resolve().is_relative_to(cache.resolve())
        assert ET.parse(path).getroot().tag == "{http://www.w3.org/2000/svg}svg"
