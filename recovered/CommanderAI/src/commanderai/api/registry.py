"""Collection ids used by the API.

| id                       | source                                                  |
|--------------------------|---------------------------------------------------------|
| ``builtin:expanded``     | commanderai-sample/expanded-collection.txt              |
| ``builtin:sample``       | commanderai-sample/sample-collection.txt                |
| ``builtin:precon:<slug>``| commanderai-sample/precons/<slug>.txt                   |
| ``default``              | COMMANDERAI_COLLECTION (if it exists and isn't a built-in)|
| ``stored:<n>``           | uploaded collection in the database                     |
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from commanderai.errors import CollectionNotFoundError
from commanderai.services.collection import parse_source
from commanderai.services.collections import get_collection, list_collections
from commanderai.services.context import ServiceContext
from commanderai.settings import PROJECT_DIR

DEFAULT_SAMPLE_DIR = PROJECT_DIR / "commanderai-sample"


@dataclass
class CollectionRef:
    id: str
    kind: str                 # builtin | default | stored
    name: str
    description: str = ""
    path: Path | None = None
    stored_id: int | None = None

    @property
    def editable(self) -> bool:
        return self.kind == "stored"


def builtin_refs(sample_dir: Path) -> list[CollectionRef]:
    refs: list[CollectionRef] = []
    expanded = sample_dir / "expanded-collection.txt"
    if expanded.exists():
        refs.append(CollectionRef(
            "builtin:expanded", "builtin", "Expanded sample",
            "Sample collection plus the five Starter Commander Decks", expanded,
        ))
    sample = sample_dir / "sample-collection.txt"
    if sample.exists():
        refs.append(CollectionRef(
            "builtin:sample", "builtin", "Original sample", "The original synthetic sample collection",
            sample,
        ))
    precons = sample_dir / "precons"
    sources = precons / "sources.json"
    decks = json.loads(sources.read_text(encoding="utf-8")).get("decks", {}) if sources.exists() else {}
    for file in sorted(precons.glob("*.txt")) if precons.exists() else []:
        meta = decks.get(file.name, {})
        title = meta.get("title") or file.stem.replace("-", " ").title()
        commander = meta.get("commander")
        refs.append(CollectionRef(
            f"builtin:precon:{file.stem}", "builtin", f"Precon: {title}",
            f"Starter Commander Deck{f' — {commander}' if commander else ''}", file,
        ))
    return refs


def all_refs(ctx: ServiceContext, sample_dir: Path) -> list[CollectionRef]:
    builtins = builtin_refs(sample_dir)
    refs: list[CollectionRef] = []
    default = ctx.settings.default_collection
    if default.exists() and default.resolve() not in {r.path.resolve() for r in builtins if r.path}:
        refs.append(CollectionRef(
            "default", "default", "My collection", f"Default collection ({default.name})", default,
        ))
    refs += builtins
    refs += [
        CollectionRef(f"stored:{c.id}", "stored", c.name, "Uploaded collection", stored_id=c.id)
        for c in list_collections(ctx)
    ]
    return refs


def default_collection_id(ctx: ServiceContext, sample_dir: Path) -> str | None:
    """The collection the UI should start with: COMMANDERAI_COLLECTION if available."""
    refs = all_refs(ctx, sample_dir)
    default = ctx.settings.default_collection
    if default.exists():
        for ref in refs:
            if ref.path and ref.path.resolve() == default.resolve():
                return ref.id
    return refs[0].id if refs else None


def resolve_ref(ctx: ServiceContext, collection_id: str, sample_dir: Path) -> CollectionRef:
    if collection_id.startswith("stored:"):
        try:
            stored_id = int(collection_id.split(":", 1)[1])
        except ValueError:
            stored_id = -1
        stored = get_collection(ctx, stored_id)  # raises CollectionNotFoundError
        return CollectionRef(collection_id, "stored", stored.name, "Uploaded collection", stored_id=stored.id)
    for ref in all_refs(ctx, sample_dir):
        if ref.id == collection_id:
            return ref
    raise CollectionNotFoundError(
        f"Collection '{collection_id}' not found", id=collection_id, kind="collection"
    )


def ref_source(ctx: ServiceContext, ref: CollectionRef) -> Path | str:
    """What the services load: a file path, or the stored collection's text."""
    if ref.stored_id is not None:
        return get_collection(ctx, ref.stored_id).content or ""
    assert ref.path is not None
    return ref.path


def ref_label(ref: CollectionRef) -> str:
    return f"{ref.name} [{ref.id}]"


def ref_counts(ctx: ServiceContext, ref: CollectionRef) -> tuple[int, int]:
    """(parsed lines, total copies) without touching the card catalog."""
    if ref.stored_id is not None:
        stored = get_collection(ctx, ref.stored_id)
        return stored.entries, stored.copies
    entries = parse_source(ref.path) if ref.path else []
    return len(entries), sum(e.quantity for e in entries)


def ref_for_path(ctx: ServiceContext, path: str | None, sample_dir: Path) -> str | None:
    """Map a collection file path (as recorded in a CLI build) back to a collection id."""
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    for ref in all_refs(ctx, sample_dir):
        if ref.path and ref.path.resolve() == target.resolve():
            return ref.id
    return None
