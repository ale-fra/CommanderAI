#!/usr/bin/env bash
# Before/after walkthrough of the phase-D bug fixes (D1-D6).
#
#   scripts/demo_fixes.sh
#
# For each fix: the 0.7.0 output (read from tests/golden/baseline/, captured
# from the original code) and the live output of the current code, plus what
# you should see. Runs offline in a throwaway directory.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CAI="$ROOT/.venv/bin/commanderai"
BASE="$ROOT/tests/golden/baseline"
[[ -x "$CAI" ]] || { echo "Run scripts/setup.sh first." >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cai-fixes-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

export COMMANDERAI_CACHE="$ROOT/offline-data"
export COMMANDERAI_COLLECTION="$ROOT/commanderai-sample/expanded-collection.txt"
export COMMANDERAI_DECKS_DIR=decks COMMANDERAI_DB=demo.db ANTHROPIC_API_KEY= COMMANDERAI_OFFLINE=1
export COLUMNS=120
P="$ROOT/commanderai-sample/precons"

commanderai() { "$CAI" "$@"; }
quiet() { grep -vE '^\s*(⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏)|^Loaded [0-9]+ Commander-legal' || true; }

fix() { printf '\n\033[1;36m━━━ %s\033[0m\n' "$*"; }
before() {  # baseline-case, grep pattern
    printf '\033[2m  0.7.0 (from tests/golden/baseline/%s):\033[0m\n' "$1"
    grep -hE "$2" "$BASE/$1"/step*.out | sed 's/^/    │ /'
}
now() {  # expectation, command line
    printf '\033[2m  now:  $ %s\n        expect: %s\033[0m\n' "$2" "$1"
    eval "$2" 2>&1 | quiet | sed 's/^/    │ /'
}

fix "D1  validate counts quantities (\"15 Plains\" = 15 cards)"
before validate-precon-first-flight "valid|✗"
now "'Deck is valid! (100 cards)' for all five precons" \
    "for d in 'first-flight:Isperia, Supreme Judge' 'grave-danger:Gisa and Geralf' 'chaos-incarnate:Kardur, Doomscourge' 'draconic-destruction:Atarka, World Render' 'token-triumph:Emmara, Soul of the Accord'; do printf '%-22s' \"\${d%%:*}\"; commanderai validate -d \"$P/\${d%%:*}.txt\" -C \"\${d#*:}\" | quiet; done"
now "new checks: partners must be able to pair; duplicates are still caught" \
    "commanderai validate -d '$P/first-flight.txt' -C 'Isperia, Supreme Judge' -P 'Gisa and Geralf' || true"

fix "D2  one price rule, and the budget includes the commander"
before build-atarka-budget40 "deck fits at|Est. price"
now "'deck fits at \$X' and 'Est. price: \$X' show the SAME amount" \
    "commanderai build -C 'Atarka, World Render' --no-llm --budget 40 | grep -E 'Budget|Est. price'"
now "a warning when the commander alone costs more than the budget (then the build stops: nothing affordable left)" \
    "commanderai build -C 'Gargos, Vicious Watcher' --no-llm --budget 1 | grep -E 'Budget|Not enough' || true"

fix "D3  power brackets work offline (Commander Spellbook unreachable / COMMANDERAI_OFFLINE=1)"
before build-zaxara-bracket2 "[Bb]racket|Rhystic Study|Mystical Tutor"
now "an 'offline rules' warning, Rhystic Study + Mystical Tutor excluded (game changers)" \
    "commanderai build -C 'Zaxara, the Exemplary' --no-llm -b 2 | grep -E 'Bracket|✗|remaining'"
now "0 — neither game changer is in the saved deck" \
    "grep -cE 'Rhystic Study|Mystical Tutor' decks/zaxara__the_exemplary.txt || true"
now "bracket 3 keeps up to 3 game changers and prioritises them" \
    "commanderai build -C 'Zaxara, the Exemplary' --no-llm -b 3 | grep -E 'Bracket|Prioritized'"

fix "D4  list decks card count"
before list-decks-after-builds "\\([0-9]+ cards\\)"
now "100 cards (the list now comes from the deck database)" \
    "commanderai list decks | grep -E '#'"

fix "D5  token list"
before tokens-built-deck "— Food|— Treasure|tapped|Created by: Cemetery"
now "'Artifact — Food', 'Artifact — Treasure', no 'tapped Zombie', a 'Copy of a permanent' entry" \
    "commanderai tokens -d decks/zaxara__the_exemplary.txt | grep -E -A1 'Food|Treasure|Zombie$|Copy' | grep -v '^--'"

fix "D6  COMMANDERAI_OFFLINE=1 disables network calls"
now "'Offline mode (COMMANDERAI_OFFLINE=1): not downloading.'" \
    "commanderai update-data || true"

printf '\n\033[32mDone.\033[0m Details: tests/golden/CHANGES.md (Phase D).\n'
