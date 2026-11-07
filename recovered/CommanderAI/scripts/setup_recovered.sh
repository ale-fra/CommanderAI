#!/usr/bin/env bash
# Setup for the recovered copy, using the explicitly identified local fixtures.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
    cp .env.recovery.example .env
fi
exec ./scripts/setup.sh "$@"
