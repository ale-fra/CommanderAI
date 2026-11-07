"""Local card images, located through the offline image manifest."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from commanderai.models import PublicModel

_lock = threading.Lock()
_cache: dict[str, ImageIndex] = {}


class CardImages(PublicModel):
    front: str | None = None     # URL of the front (or only) face
    back: str | None = None      # URL of the back face (double-faced cards)


class ImageIndex:
    """Card name → image file names, from ``<cache>/image-manifest.json``."""

    def __init__(self, manifest: Path):
        self.root = manifest.parent
        self.by_name: dict[str, dict[str, str]] = {}
        if manifest.exists():
            for entry in json.loads(manifest.read_text(encoding="utf-8")):
                face = "back" if entry.get("face_index") == 1 else "front"
                file = Path(entry["local_path"]).name
                self.by_name.setdefault(entry["name"], {})[face] = file

    def images(self, name: str, url_prefix: str = "/api/images") -> CardImages:
        files = self.by_name.get(name, {})
        return CardImages(
            front=f"{url_prefix}/{files['front']}" if "front" in files else None,
            back=f"{url_prefix}/{files['back']}" if "back" in files else None,
        )

    @property
    def directory(self) -> Path:
        return self.root / "images"


def image_index(cache_dir: Path) -> ImageIndex:
    key = str(cache_dir.resolve())
    with _lock:
        if key not in _cache:
            _cache[key] = ImageIndex(cache_dir / "image-manifest.json")
        return _cache[key]
