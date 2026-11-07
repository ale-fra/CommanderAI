#!/usr/bin/env bash
# Verify the recovered code with the data actually available in this checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/test.sh lint web
.venv/bin/python -m pytest -q --ignore=tests/test_api.py
.venv/bin/python scripts/verify_recovery.py
