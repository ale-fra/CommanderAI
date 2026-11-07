"""Print the OpenAPI schema: ``python -m commanderai.api.openapi > web/openapi.json``."""

import json
import sys
from pathlib import Path

from commanderai.api.app import create_app
from commanderai.settings import Settings


def schema() -> dict:
    # The schema doesn't depend on settings; use inert ones (no database touched).
    settings = Settings(decks_dir=Path("decks"), default_collection=Path("collection.txt"),
                        cache_dir=Path("offline-data"), db_path=Path("unused.db"), offline=True)
    return create_app(settings, web_dist=None).openapi()


def main() -> None:
    json.dump(schema(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
