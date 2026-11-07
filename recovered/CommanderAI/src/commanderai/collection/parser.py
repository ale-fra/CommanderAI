import csv
import io
import re
from pathlib import Path

from commanderai.models import CollectionEntry

_LINE_PATTERN = re.compile(
    r"^(\d+)x?\s+(.+?)(?:\s+\(([A-Za-z0-9]+)\))?(?:\s+(\d+))?$"
)

_CSV_HEADERS = {"name", "card", "card name", "cardname"}


def parse_collection(source: str | Path) -> list[CollectionEntry]:
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source

    lines = text.strip().splitlines()
    if not lines:
        return []

    # Find first non-comment, non-empty line to detect format
    first_content = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
            first_content = stripped
            break

    if not first_content:
        return []

    if _looks_like_csv(first_content):
        # Strip comment lines before CSV parsing
        csv_lines = [l for l in lines if not l.strip().startswith("#") and not l.strip().startswith("//")]
        return _parse_csv("\n".join(csv_lines))
    return _parse_text(lines)


def _looks_like_csv(first_line: str) -> bool:
    lower = first_line.lower()
    return "," in lower and any(h in lower for h in _CSV_HEADERS)


# Annotations added by deck exports that should be stripped before matching:
#   archidekt slot tags  -> "1 Sol Ring [Ramp]"
#   moxfield markers      -> "1 Sol Ring *CMDR*"
#   our text format       -> "1 Sol Ring  {2}  // reason"
_SLOT_TAG_RE = re.compile(r"\s*\[[^\]]*\]\s*$")
_MARKER_RE = re.compile(r"\s*\*[^*]*\*")
_MANA_TAIL_RE = re.compile(r"\s*\{[^}]*\}.*$")


def _clean_card_line(line: str) -> str:
    line = _MARKER_RE.sub("", line)
    line = _SLOT_TAG_RE.sub("", line)
    line = _MANA_TAIL_RE.sub("", line)
    return line.strip()


def _parse_text(lines: list[str]) -> list[CollectionEntry]:
    entries = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # Skip structural lines from our human-readable deck format.
        if line.startswith("===") or line.startswith("---"):
            continue

        line = _clean_card_line(line)
        if not line:
            continue

        match = _LINE_PATTERN.match(line)
        if match:
            qty = int(match.group(1))
            name = match.group(2).strip()
            set_code = match.group(3)
            collector_num = match.group(4)
            entries.append(
                CollectionEntry(
                    quantity=qty,
                    card_name=name,
                    set_code=set_code,
                    collector_number=collector_num,
                )
            )
        else:
            name = line.strip()
            if name:
                entries.append(CollectionEntry(quantity=1, card_name=name))

    return entries


def _parse_csv(text: str) -> list[CollectionEntry]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    field_map = {f.lower().strip(): f for f in reader.fieldnames}
    name_field = None
    for candidate in ["name", "card name", "cardname", "card"]:
        if candidate in field_map:
            name_field = field_map[candidate]
            break

    if not name_field:
        return []

    qty_field = None
    for candidate in ["quantity", "count", "qty", "amount"]:
        if candidate in field_map:
            qty_field = field_map[candidate]
            break

    set_field = None
    for candidate in ["set", "edition", "set code", "setcode", "edition code"]:
        if candidate in field_map:
            set_field = field_map[candidate]
            break

    entries = []
    for row in reader:
        name = row.get(name_field, "").strip()
        if not name:
            continue
        qty = 1
        if qty_field and row.get(qty_field):
            try:
                qty = int(row[qty_field])
            except ValueError:
                qty = 1
        set_code = row.get(set_field, "").strip() if set_field else None
        entries.append(
            CollectionEntry(quantity=qty, card_name=name, set_code=set_code or None)
        )

    return entries


def aggregate_entries(entries: list[CollectionEntry]) -> list[CollectionEntry]:
    """Merge duplicate card names, summing quantities."""
    by_name: dict[str, CollectionEntry] = {}
    for entry in entries:
        key = entry.card_name.lower()
        if key in by_name:
            by_name[key].quantity += entry.quantity
        else:
            by_name[key] = CollectionEntry(
                quantity=entry.quantity,
                card_name=entry.card_name,
                set_code=entry.set_code,
                collector_number=entry.collector_number,
            )
    return list(by_name.values())


def convert_to_text(entries: list[CollectionEntry]) -> str:
    """Convert parsed entries to simple '1 CardName' text format."""
    aggregated = aggregate_entries(entries)
    aggregated.sort(key=lambda e: e.card_name.lower())
    lines = [f"{e.quantity} {e.card_name}" for e in aggregated]
    return "\n".join(lines)
