#!/usr/bin/env bash
# Guided manual tour of the web UI.
#
#   scripts/demo_ui.sh              throwaway database (your own decks are untouched)
#   scripts/demo_ui.sh --mine       use your own data (.env / COMMANDERAI_* settings)
#   PORT=8800 scripts/demo_ui.sh    another port (default 8790)
#
# Starts `commanderai serve`, seeds two decks (throwaway mode), prints what to try
# on every screen and what you should see, then keeps running until Ctrl+C.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PORT="${PORT:-8790}"
BASE="http://127.0.0.1:$PORT"
MINE=0
[[ "${1:-}" == "--mine" ]] && MINE=1

[[ -x .venv/bin/commanderai ]] || { echo "Run scripts/setup.sh first." >&2; exit 2; }
[[ -f web/dist/index.html ]] || { echo "The UI is not built: run scripts/setup.sh (needs Node.js >= 22.12)." >&2; exit 2; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 2; }

WORK=""
SERVER_PID=""
cleanup() {
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
    [[ -n "$WORK" ]] && rm -rf "$WORK"
    printf '\nServer stopped.\n'
}
trap cleanup EXIT INT TERM

if [[ $MINE -eq 0 ]]; then
    WORK="$(mktemp -d "${TMPDIR:-/tmp}/cai-ui-XXXXXX")"
    export COMMANDERAI_CACHE="$ROOT/offline-data"
    export COMMANDERAI_COLLECTION="$ROOT/commanderai-sample/expanded-collection.txt"
    export COMMANDERAI_DECKS_DIR="$WORK/decks" COMMANDERAI_DB="$WORK/demo.db"
    export COMMANDERAI_OFFLINE=1 ANTHROPIC_API_KEY=
fi

.venv/bin/commanderai serve --port "$PORT" >"${WORK:-/tmp}/cai-ui-server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do curl -sf "$BASE/api/status" >/dev/null && break; sleep 0.25; done
curl -sf "$BASE/api/status" >/dev/null || { echo "Server did not start:"; cat "${WORK:-/tmp}/cai-ui-server.log"; exit 1; }

if [[ $MINE -eq 0 ]]; then
    seed() {  # commander, extra json, name
        local id
        id=$(curl -sf -X POST "$BASE/api/builds" -H 'Content-Type: application/json' \
            -d "{\"collection\": \"builtin:expanded\", \"commander\": \"$1\"$2}" | sed -E 's/.*"build_id":"([0-9a-f]+)".*/\1/')
        curl -sf -X POST "$BASE/api/decks" -H 'Content-Type: application/json' \
            -d "{\"build_id\": \"$id\", \"name\": \"$3\"}" >/dev/null
    }
    seed "Atarka, World Render" ', "theme": "dragons"' "Demo: Atarka dragons"
    seed "Emmara, Soul of the Accord" ', "budget": 80' "Demo: Emmara on a budget"
fi

b() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
do_() { printf '  \033[1mDo:\033[0m     %s\n' "$*"; }
see() { printf '  \033[2mExpect:\033[0m %s\n' "$*"; }

cat <<EOF

$(printf '\033[32mCommanderAI is running →\033[0m') $BASE
$( [[ $MINE -eq 0 ]] && echo "(throwaway data in $WORK — two demo decks were saved)" || echo "(your own data)")
Open the address in a browser, then follow the checklist. Press Ctrl+C to stop.
EOF

b "1. Shell"
do_ "Open $BASE"
see "Dark theme, Collection page, 'Expanded sample (796)' selected in the header, 'Offline' badge."
do_ "Click the sun icon (top right), then reload the page"
see "Light theme, kept after the reload. Switch back if you like."
do_ "Narrow the window below ~760 px (or open it on a phone)"
see "The menu moves into the ☰ button; the collection selector is inside the menu."

b "2. Collection"
see "'Showing 500 of 500 cards', card images loading as you scroll."
do_ "Type 'dragon' in the search box"
see "Only dragon-related cards; the URL contains q=dragon (try reloading: the search stays)."
do_ "Clear the search; in Color identity click Blue and Green, choose 'Exactly', switch on 'Commanders only'"
see "Showing 4 cards (Tatyova, Inga and Esika, Ezuri, Zegana)."
do_ "Click a card (e.g. 'Invasion of Zendikar // Awakened Skyclave' via search 'invasion')"
see "Detail dialog: both faces' text, price, EDHREC rank, 'Owned' count; 'Show back' flips the image."
do_ "Press Upload, paste: 1 Sol Ring / 1 Arcane Signat / 1 Not A Real Card / 1 Zaxara, the Exemplary, name it, press 'Check cards'"
see "'1 name(s) corrected: Arcane Signat → Arcane Signet' and '1 card(s) not found'. Save makes it the active collection;"
see "the ⋯ menu next to Upload can rename / replace / delete it (built-in collections can't be changed)."

b "3. Commanders"
see "27 commanders with images, supporting-card counts and EDHREC rank."
do_ "Click the red mana symbol"
see "3 commanders (Drakuseth, Kazuul, Verix)."
do_ "Press 'Suggest a commander', pick theme 'Tokens', press Suggest"
see "A ranked table with Zaxara first; 'Build' opens the builder with commander and theme filled in."

b "4. Build"
do_ "Choose commander 'Zaxara, the Exemplary', press 'Build deck'"
see "100 cards grouped by role with pick reasons, price (\$280.20), 'N cards without price data', average mana value."
do_ "Open the Stats, Tokens and Build log tabs"
see "Mana curve and roles-vs-targets charts, color symbols, card types; Food/Treasure/Zombie tokens; the build log."
do_ "Press Rebuild, then Re-roll"
see "Rebuild = same deck. Re-roll = a different deck and a 'Seed N' badge (enter that seed later to get it back)."
do_ "Set Budget 120 and Power bracket 2, build again"
see "'Budget \$… / \$120.00' badge and a Heads-up box: offline bracket rules, Rhystic Study excluded as a game changer."
do_ "Switch to Auto-pick, choose theme 'Dragon', build"
see "An 'Auto-picked' badge and a dragon commander."
do_ "Press Save, keep or change the name"
see "You land on the saved deck's page."

b "5. Decks"
see "The library: saved decks with commander thumbnails, colors, price, source and date."
do_ "Search 'emmara'; try the source filter; use a row's ⋯ menu to rename or download"
see "The list narrows; downloads are Moxfield / JSON files."
do_ "Tick two decks and press Compare"
see "Cards only in A, only in B, and shared (with copy changes such as 'Forest 9 → 13')."
do_ "Open a deck: tabs Cards / Stats / Tokens / Legality / Build info / Notes"
see "'This deck is legal'; Build info shows the settings and 'Rebuild with these settings' (builds the same deck)."
do_ "Export ▸ copy 'Moxfield', then Decks ▸ Import, paste it"
see "A new 'Imported' deck with the same cards."

b "6. About"
see "Catalog snapshot, offline mode, counts of saved decks and uploaded collections; link to the API docs (/api/docs)."

printf '\n\033[2mWaiting… (Ctrl+C to stop the server)\033[0m\n'
wait "$SERVER_PID"
