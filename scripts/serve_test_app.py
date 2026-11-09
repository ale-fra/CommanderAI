#!/usr/bin/env python3
"""Serve the real API/UI with bundled integration data for browser tests."""

import argparse
from pathlib import Path

import uvicorn

from commanderai.api import create_app
from commanderai.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures/integration"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    # Playwright provides fresh database/deck paths; API keys are always empty.
    settings = Settings.from_env().with_overrides(
        cache_dir=FIXTURES / "catalog",
        default_collection=FIXTURES / "collections/expanded-collection.txt",
        anthropic_api_key="",
        offline=True,
    )
    app = create_app(settings, sample_dir=FIXTURES / "collections")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
