#!/usr/bin/env bash
# Guided tour of the deck database (phase C), run in a throwaway directory.
#
#   scripts/demo_deck_library.sh           run and explain every step
#   scripts/demo_deck_library.sh --keep    keep the scratch directory afterwards
#
# Each step prints what it does and what you should see. Nothing outside the
# scratch directory is touched (your own decks/ and data/commanderai.db are safe).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CAI="$ROOT/.venv/bin/commanderai"
[[ -x "$CAI" ]] || { echo "Run scripts/setup.sh first." >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cai-demo-XXXXXX")"
if [[ "${1:-}" == "--keep" ]]; then
    echo "Scratch directory (kept): $WORK"
else
    trap 'rm -rf "$WORK"' EXIT
fi
cd "$WORK"

export COMMANDERAI_CACHE="$ROOT/offline-data"
export COMMANDERAI_COLLECTION="$ROOT/commanderai-sample/expanded-collection.txt"
export COMMANDERAI_DECKS_DIR=decks
export COMMANDERAI_DB=demo.db
export ANTHROPIC_API_KEY=
export COMMANDERAI_OFFLINE=1
export COLUMNS=120

n=0
commanderai() { "$CAI" "$@"; }
step() {  # title, expectation, command line (as you would type it)
    local title="$1" expect="$2" cmd="$3"
    n=$((n + 1))
    printf '\n\033[1m[%d] %s\033[0m\n' "$n" "$title"
    printf '\033[2m    $ %s\n    expect: %s\033[0m\n' "$cmd" "$expect"
    eval "$cmd" 2>&1 | grep -vE '^\s*(⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏)' | sed 's/^/    │ /' || true
}

# Pre-existing "legacy" deck files, as CommanderAI 0.7.0 wrote them.
mkdir -p decks
cp "$ROOT/tests/golden/baseline/build-zaxara/decks/zaxara__the_exemplary.txt" decks/
cp "$ROOT/tests/golden/baseline/build-format-archidekt/decks/emmara__soul_of_the_accord.txt" decks/

step "Legacy migration: the first library command imports the old .txt decks" \
     "'Imported 2 legacy deck file(s)…', then decks #1 and #2 with source 'legacy'" \
     "commanderai list decks"

step "Build a deck: it is stored in the database AND exported to decks/" \
     "budget lines, then 'Deck saved → decks/atarka__world_render.txt (deck #3)'; 'deck fits at' equals 'Est. price' (commander included)" \
     "commanderai build -C 'Atarka, World Render' --no-llm --budget 60 --theme dragons | grep -E 'Budget|Deck saved|Est. price'"

step "List the library (newest first)" \
     "three decks: #3 (cli), #2 and #1 (legacy)" \
     "commanderai decks list"

step "Show a deck with its build parameters" \
     "'Build: theme dragon · budget \$60.00 · lands 37' followed by the grouped deck list" \
     "commanderai decks show 3 | head -12"

step "Export as a re-importable JSON document" \
     "'Exported deck #3 (json) → atarka.json'" \
     "commanderai decks export 3 -f json -o atarka.json"

step "Export as a Moxfield list (printed to stdout)" \
     "'1 Atarka, World Render *CMDR*' then 99 lines" \
     "commanderai decks export 3 -f moxfield | head -5"

step "Import the JSON back under a new name" \
     "'Imported deck #4 — Atarka copy (100 cards)'" \
     "commanderai decks import atarka.json --name 'Atarka copy'"

step "Rename and delete" \
     "'Renamed deck #1 → My first Zaxara' and 'Deleted deck #2 — emmara__soul_of_the_accord'" \
     "commanderai decks rename 1 'My first Zaxara' && commanderai decks delete 2"

step "Re-run the migration: deleted decks are NOT resurrected from their files" \
     "'No new deck files to import (3 scanned, 3 already known).'" \
     "commanderai decks migrate"

step "Errors are friendly" \
     "'Deck #42 not found' (exit code 1)" \
     "commanderai decks show 42 || echo \"(exit code \$?)\""

step "Final library" \
     "#4 Atarka copy, #3 Atarka, #1 My first Zaxara" \
     "commanderai decks list"

if [[ "${1:-}" == "--keep" ]]; then
    printf '\n\033[32mDemo finished.\033[0m Database kept at %s/demo.db\n' "$WORK"
else
    printf '\n\033[32mDemo finished.\033[0m Scratch directory removed (use --keep to inspect it).\n'
fi
