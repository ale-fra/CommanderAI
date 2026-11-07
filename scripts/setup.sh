#!/usr/bin/env bash
# One-command environment setup for CommanderAI.
#
#   scripts/setup.sh              create/update .venv and install everything
#   scripts/setup.sh --recreate   delete .venv first and start from scratch
#
# What it does:
#   1. checks Python >= 3.11 (override the interpreter with PYTHON=/path/to/python3)
#   2. creates .venv (if missing) and installs CommanderAI + web server + dev tools
#   3. writes a .env with the bundled demo catalog + sample collection
#      (only if .env does not exist yet — an existing .env is never touched)
#   4. builds the web UI (web/dist) if Node.js >= 22.12 is available
#   5. runs a smoke test
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PYTHON="${PYTHON:-python3}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mSETUP FAILED:\033[0m %s\n' "$*" >&2; exit 1; }

step "Checking Python"
command -v "$PYTHON" >/dev/null || fail "'$PYTHON' not found. Install Python 3.11+ or set PYTHON=/path/to/python3."
"$PYTHON" - <<'EOF' || fail "Python 3.11 or newer is required."
import sys
print(f"Python {sys.version.split()[0]} at {sys.executable}")
sys.exit(0 if sys.version_info >= (3, 11) else 1)
EOF

if [[ "${1:-}" == "--recreate" ]]; then
    step "Removing existing .venv"
    rm -rf .venv
fi

if [[ ! -x .venv/bin/python ]]; then
    step "Creating virtual environment in .venv"
    "$PYTHON" -m venv .venv
else
    step "Reusing existing .venv"
fi

step "Installing CommanderAI, the web server (FastAPI) and dev tools (pytest, ruff)"
.venv/bin/python -m pip install --quiet --disable-pip-version-check -e '.[dev,web]' \
    || fail "pip install failed. Without package-index access, pre-download the wheels and use:
       .venv/bin/pip install --no-index --find-links <wheel-dir> -e '.[dev,web]'"

if [[ ! -f .env ]]; then
    step "Writing .env (demo catalog + sample collection)"
    cat > .env <<EOF
# Written by scripts/setup.sh — offline defaults. Shell variables take precedence.
COMMANDERAI_CACHE=$ROOT/data/demo-catalog
COMMANDERAI_COLLECTION=$ROOT/data/collezione-fittizia.csv
COMMANDERAI_DECKS_DIR=$ROOT/decks
COMMANDERAI_DB=$ROOT/data/commanderai.db
# Never call external services (Commander Spellbook, Claude, Scryfall downloads).
# Brackets then use the offline rules. Set to 0 when network access is available.
COMMANDERAI_OFFLINE=1
# ANTHROPIC_API_KEY=YOUR_API_KEY_HERE   (only for AI features; needs network access)
EOF
else
    step "Keeping existing .env"
fi

step "Building the web UI (web/dist)"
WEB_BUILT=0
if command -v node >/dev/null && command -v npm >/dev/null; then
    if node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=12)?0:1)'; then
        (cd web && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent) \
            || fail "building the web UI failed (see the output above)"
        WEB_BUILT=1
    else
        printf '  \033[33mNode.js %s found; the web UI needs >= 22.12 — skipping the UI build.\033[0m\n' "$(node --version)"
    fi
else
    printf '  \033[33mNode.js not found — skipping the UI build (the CLI works without it).\033[0m\n'
fi

step "Smoke test: commanderai list commanders --head 3"
.venv/bin/commanderai list commanders --head 3 || fail "the CLI did not run"

cat <<EOF

$(printf '\033[32mSetup complete.\033[0m')

  Activate the environment:   source .venv/bin/activate
  Run the CLI:                commanderai --help
  Start the web UI:           commanderai serve        → http://127.0.0.1:8000
  Run all tests:              scripts/test.sh          (see docs/TESTING.md)
EOF
if [[ $WEB_BUILT -ne 1 ]]; then
    printf '\033[33mNote: the web UI was not built (install Node.js >= 22.12 and re-run).\033[0m\n'
fi
