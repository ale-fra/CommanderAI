import gzip
import itertools
import shutil
import tempfile
import time
from pathlib import Path

import httpx
import orjson

from commanderai.config import (
    BULK_DATA_MAX_AGE_DAYS,
    CACHE_DIR,
    ORACLE_CARDS_PATH,
    SCRYFALL_BULK_URL,
    SCRYFALL_USER_AGENT,
)
from commanderai.models import Card


def _ensure_cache_dir(cache_dir: Path | None = None):
    (cache_dir or CACHE_DIR).mkdir(parents=True, exist_ok=True)


def _is_stale(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return True
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds > max_age_days * 86400


def fetch_bulk_download_url() -> str:
    resp = httpx.get(
        SCRYFALL_BULK_URL,
        headers={"User-Agent": SCRYFALL_USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    for item in data["data"]:
        if item["type"] == "oracle_cards":
            url = item.get("download_uri") or item.get("jsonl_download_uri")
            if isinstance(url, str) and url:
                return url
            raise RuntimeError("Scryfall oracle_cards entry has no download URL")
    raise RuntimeError("oracle_cards bulk data not found in Scryfall response")


def download_bulk_data(force: bool = False, dest: Path | None = None) -> Path:
    dest = dest or ORACLE_CARDS_PATH
    _ensure_cache_dir(dest.parent)
    if not force and not _is_stale(dest, BULK_DATA_MAX_AGE_DAYS):
        return dest

    url = fetch_bulk_download_url()
    temporary_paths = []
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as downloaded:
            download_path = Path(downloaded.name)
            temporary_paths.append(download_path)
            with httpx.stream(
                "GET", url, headers={"User-Agent": SCRYFALL_USER_AGENT}, timeout=300
            ) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    downloaded.write(chunk)

        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as normalized:
            normalized_path = Path(normalized.name)
            temporary_paths.append(normalized_path)
            _normalize_bulk_data(download_path, normalized)

        # Keep the previous cache intact until download and conversion both succeed.
        normalized_path.replace(dest)
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)

    return dest


def _normalize_bulk_data(path: Path, output):
    """Keep the cache as a JSON array, including for Scryfall's gzipped JSONL feed."""
    with path.open("rb") as downloaded:
        compressed = downloaded.read(2) == b"\x1f\x8b"
    opener = gzip.open if compressed else open
    with opener(path, "rb") as source:
        first = source.read(1)
        while first and first.isspace():
            first = source.read(1)
        if not first:
            raise RuntimeError("Scryfall bulk download is empty")
        if first == b"[":
            output.write(first)
            shutil.copyfileobj(source, output)
            return

        output.write(b"[")
        separator = b""
        for line in itertools.chain([first + source.readline()], source):
            if not line.strip():
                continue
            card = orjson.loads(line)
            if not isinstance(card, dict):
                raise TypeError("Scryfall JSONL records must be card objects")
            output.write(separator)
            output.write(orjson.dumps(card))
            separator = b","
        output.write(b"]")


_NON_LEGAL_TYPES = {"plane", "phenomenon", "scheme", "vanguard", "conspiracy"}


def _read_raw(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Oracle cards not found at {path}. Run 'commanderai update-data' first."
        )
    return orjson.loads(path.read_bytes())


def _card_from_raw(c: dict) -> Card:
    oracle_text = c.get("oracle_text", "") or ""
    if not oracle_text and c.get("card_faces"):
        oracle_text = " // ".join(
            face.get("oracle_text", "") for face in c["card_faces"]
        )

    return Card(
        name=c["name"],
        mana_cost=c.get("mana_cost", "") or "",
        cmc=c.get("cmc", 0.0),
        type_line=c.get("type_line", ""),
        oracle_text=oracle_text,
        color_identity=c.get("color_identity", []),
        colors=c.get("colors", []),
        keywords=c.get("keywords", []),
        edhrec_rank=c.get("edhrec_rank"),
        power=c.get("power"),
        toughness=c.get("toughness"),
        legalities=c.get("legalities", {}),
        prices=c.get("prices", {}),
        set_code=c.get("set", ""),
        set_name=c.get("set_name", ""),
        collector_number=c.get("collector_number", ""),
        rarity=c.get("rarity", ""),
        card_faces=c.get("card_faces"),
        game_changer=bool(c.get("game_changer", False)),
    )


def _non_legal_names_from_raw(cards_data: list[dict]) -> set[str]:
    names = set()
    for c in cards_data:
        if c.get("legalities", {}).get("commander") == "legal":
            continue
        name = c.get("name", "")
        if name:
            names.add(name.lower())
            type_line = c.get("type_line", "").lower()
            if any(t in type_line for t in _NON_LEGAL_TYPES):
                names.add(name.lower())
            if c.get("card_faces"):
                for face in c["card_faces"]:
                    face_name = face.get("name", "")
                    if face_name:
                        names.add(face_name.lower())
    return names


def load_catalog_data(path: Path | None = None) -> tuple[list[Card], set[str]]:
    """Parse the oracle file once; return (commander-legal cards, non-legal names)."""
    path = path or ORACLE_CARDS_PATH
    cards_data = _read_raw(path)
    cards = [
        _card_from_raw(c) for c in cards_data
        if c.get("legalities", {}).get("commander") == "legal"
    ]
    return cards, _non_legal_names_from_raw(cards_data)


def load_cards(path: Path | None = None) -> list[Card]:
    path = path or ORACLE_CARDS_PATH
    return [
        _card_from_raw(c) for c in _read_raw(path)
        if c.get("legalities", {}).get("commander") == "legal"
    ]


def load_non_legal_names(path: Path | None = None) -> set[str]:
    """Load names of cards that exist in Scryfall but aren't Commander-legal."""
    path = path or ORACLE_CARDS_PATH
    if not path.exists():
        return set()
    return _non_legal_names_from_raw(orjson.loads(path.read_bytes()))
