import gzip

import httpx
import orjson
import pytest
import respx

from commanderai.data import scryfall


@pytest.mark.parametrize("field", ["download_uri", "jsonl_download_uri"])
@respx.mock
def test_bulk_metadata_accepts_legacy_and_jsonl_urls(field):
    url = "https://data.scryfall.io/oracle.jsonl.gz"
    respx.get(scryfall.SCRYFALL_BULK_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"type": "oracle_cards", field: url}]})
    )
    assert scryfall.fetch_bulk_download_url() == url


@respx.mock
def test_bulk_metadata_reports_missing_url():
    respx.get(scryfall.SCRYFALL_BULK_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"type": "oracle_cards"}]})
    )
    with pytest.raises(RuntimeError, match="no download URL"):
        scryfall.fetch_bulk_download_url()


@pytest.mark.parametrize("compressed_jsonl", [False, True])
@respx.mock
def test_download_keeps_cache_compatible_with_both_card_loaders(
    tmp_path, monkeypatch, compressed_jsonl
):
    cards = [
        {"name": "Sol Ring", "legalities": {"commander": "legal"}},
        {"name": "Black Lotus", "legalities": {"commander": "banned"}},
    ]
    url = "https://data.scryfall.io/oracle"
    payload = orjson.dumps(cards)
    if compressed_jsonl:
        payload = gzip.compress(b"\n".join(orjson.dumps(card) for card in cards) + b"\n")
    cache = tmp_path / "oracle_cards.json"
    monkeypatch.setattr(scryfall, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(scryfall, "ORACLE_CARDS_PATH", cache)
    monkeypatch.setattr(scryfall, "fetch_bulk_download_url", lambda: url)
    respx.get(url).mock(return_value=httpx.Response(200, content=payload))

    assert scryfall.download_bulk_data() == cache
    assert orjson.loads(cache.read_bytes()) == cards
    assert [card.name for card in scryfall.load_cards(cache)] == ["Sol Ring"]
    assert scryfall.load_non_legal_names(cache) == {"black lotus"}
    assert list(tmp_path.iterdir()) == [cache]


@pytest.mark.parametrize("payload", [b"", gzip.compress(b'{"name": "Sol Ring"}\ninvalid\n')])
@respx.mock
def test_failed_conversion_preserves_existing_cache(tmp_path, monkeypatch, payload):
    cache = tmp_path / "oracle_cards.json"
    cache.write_bytes(b"[]")
    url = "https://data.scryfall.io/oracle"
    monkeypatch.setattr(scryfall, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(scryfall, "ORACLE_CARDS_PATH", cache)
    monkeypatch.setattr(scryfall, "fetch_bulk_download_url", lambda: url)
    respx.get(url).mock(return_value=httpx.Response(200, content=payload))

    with pytest.raises((RuntimeError, ValueError)):
        scryfall.download_bulk_data(force=True)
    assert cache.read_bytes() == b"[]"
    assert list(tmp_path.iterdir()) == [cache]


@respx.mock
def test_download_uses_explicit_destination_with_atomic_jsonl_conversion(tmp_path, monkeypatch):
    destination = tmp_path / "custom" / "oracle_cards.json"
    default = tmp_path / "unused-default.json"
    monkeypatch.setattr(scryfall, "ORACLE_CARDS_PATH", default)
    monkeypatch.setattr(scryfall, "fetch_bulk_download_url", lambda: "https://data.scryfall.io/cards")
    card = {"name": "Sol Ring", "legalities": {"commander": "legal"}}
    respx.get("https://data.scryfall.io/cards").mock(
        return_value=httpx.Response(200, content=gzip.compress(orjson.dumps(card) + b"\n"))
    )
    assert scryfall.download_bulk_data(dest=destination) == destination
    assert orjson.loads(destination.read_bytes()) == [card]
    assert not default.exists()
    assert list(destination.parent.iterdir()) == [destination]
