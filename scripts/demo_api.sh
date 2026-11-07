#!/usr/bin/env bash
# Guided tour of the HTTP API (M1) against a real `commanderai serve`.
#
#   scripts/demo_api.sh            start a throwaway server, call every endpoint group
#   scripts/demo_api.sh --keep     keep the scratch directory (database) afterwards
#
# Each step prints the request, what you should see, and a short summary of the
# actual response. Uses a scratch database and decks folder; your own data is
# never touched. Interactive API docs while a server runs: http://127.0.0.1:<port>/api/docs
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Run scripts/setup.sh first." >&2; exit 2; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 2; }

PORT="${PORT:-8791}"
BASE="http://127.0.0.1:$PORT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cai-api-XXXXXX")"
SERVER_PID=""
cleanup() {
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
    if [[ "${1:-}" != "--keep" ]]; then rm -rf "$WORK"; fi
}
trap 'cleanup "${KEEP:-}"' EXIT
[[ "${1:-}" == "--keep" ]] && KEEP="--keep"

echo "Starting commanderai serve on $BASE (scratch dir $WORK)…"
COMMANDERAI_CACHE="$ROOT/offline-data" \
COMMANDERAI_COLLECTION="$ROOT/commanderai-sample/expanded-collection.txt" \
COMMANDERAI_DECKS_DIR="$WORK/decks" COMMANDERAI_DB="$WORK/demo.db" \
COMMANDERAI_OFFLINE=1 ANTHROPIC_API_KEY= \
    "$ROOT/.venv/bin/commanderai" serve --port "$PORT" >"$WORK/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do curl -sf "$BASE/api/status" >/dev/null && break; sleep 0.2; done
curl -sf "$BASE/api/status" >/dev/null || { echo "server did not start:"; cat "$WORK/server.log"; exit 1; }

n=0
# step TITLE EXPECT METHOD PATH [JSON-BODY | @FILE] — then a python expression summarising `r`
step() {
    local title="$1" expect="$2" method="$3" path="$4" body="${5:-}" summary="${6:-r}"
    n=$((n + 1))
    local shown="$body"
    [[ "$body" == @* ]] && shown="(JSON body from ${body#@})"
    printf '\n\033[1m[%d] %s\033[0m\n' "$n" "$title"
    printf '\033[2m    %s %s%s\n    expect: %s\033[0m\n' "$method" "$path" "${shown:+  $shown}" "$expect"
    local args=(-s -o "$WORK/resp" -w '%{http_code}' -X "$method" "$BASE$path")
    [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data-binary "$body")
    local code
    code=$(curl "${args[@]}")
    "$PY" - "$code" "$WORK/resp" "$summary" <<'PYEOF'
import json, sys
code, path, expr = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(path, encoding="utf-8").read()
try:
    r = json.loads(raw) if raw.strip() else None
except json.JSONDecodeError:
    r = raw
try:
    out = eval(expr, {"r": r, "len": len, "sum": sum, "sorted": sorted})
except Exception as e:  # show the raw body when the summary doesn't apply (e.g. errors)
    out = r
text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
print(f"    │ HTTP {code}  {text[:400]}")
PYEOF
}
jq_id() { "$PY" -c "import json,sys; print(json.load(open('$WORK/resp'))$1)"; }

step "Status" "500 catalog cards, offline, default collection builtin:expanded" \
    GET /api/status "" "{'catalog': r['catalog'], 'offline': r['offline'], 'default_collection': r['default_collection'], 'database': r['database']}"

step "Collections" "builtin:expanded (796 copies), builtin:sample, five precons" \
    GET /api/collections "" "[(c['id'], c['copies']) for c in r]"

step "Collection cards (filtered client-side by the UI)" "500 cards; Sol Ring quantity 6" \
    GET "/api/collections/builtin:expanded/cards" "" "{'cards': len(r), 'copies': sum(c['quantity'] for c in r), 'sol_ring': [c['quantity'] for c in r if c['name']=='Sol Ring']}"

step "Card detail (name in the query string: it may contain '/')" "two faces, front and back images" \
    GET "/api/card?name=Invasion%20of%20Zendikar%20//%20Awakened%20Skyclave" "" "{'faces': [f['name'] for f in r['faces']], 'images': r['images']}"

step "Commanders" "27 commanders; Zaxara has 334 supporting cards" \
    GET "/api/commanders?collection=builtin:expanded" "" "{'count': len(r), 'first': r[0]['card']['name'], 'zaxara_support': [c['support'] for c in r if c['card']['name'].startswith('Zaxara')]}"

step "Commander suggestions for a theme" "Zaxara first for tokens" \
    GET "/api/commanders/suggestions?collection=builtin:expanded&theme=tokens&top=3" "" "[s['commander']['card']['name'] for s in r['suggestions']]"

step "Upload preview (nothing saved)" "1 fuzzy correction, 1 unmatched card" \
    POST /api/collections/preview '{"content": "1 Sol Ring\n1 Arcane Signat\n1 Not A Card\n1 Zaxara, the Exemplary"}' \
    "{'unique_cards': r['unique_cards'], 'fuzzy': r['match']['fuzzy'], 'unmatched': r['match']['unmatched']}"

step "Build a preview (not saved yet)" "100 cards, stats, tokens, build log; seed returned" \
    POST /api/builds '{"collection": "builtin:expanded", "commander": "Atarka, World Render", "budget": 60, "bracket": 2, "variety": 0.5}' \
    "{'build_id': r['result'] and r['build_id'][:8]+'…', 'cards': r['result']['stats']['card_count'], 'price': r['result']['stats']['total_price'], 'seed': r['result']['params']['seed'], 'bracket_mode': r['result']['report']['bracket']['mode'], 'notices': [n['code'] for n in r['result']['report']['notices']][:6]}"
BUILD_ID=$(jq_id "['build_id']")

step "Save the preview" "201, deck #1 with its build parameters" \
    POST /api/decks "{\"build_id\": \"$BUILD_ID\", \"name\": \"Budget Atarka\"}" \
    "{'id': r['id'], 'name': r['name'], 'source': r['source'], 'params': r['params']}"

step "Deck library" "total 1, newest first, with a commander image" \
    GET "/api/decks?limit=10" "" "{'total': r['total'], 'items': [(d['id'], d['name'], d['card_count'], d['commander_image'][:20]+'…') for d in r['items']]}"

step "Rename + notes" "name and notes updated" \
    PATCH /api/decks/1 '{"name": "Budget Atarka v2", "notes": "Needs more dragons"}' "{'name': r['name'], 'notes': r['notes']}"

step "Export as Moxfield text" "first line '1 Atarka, World Render *CMDR*'" \
    GET "/api/decks/1/export?format=moxfield" "" "r.splitlines()[:3]"

curl -s "$BASE/api/decks/1/export?format=json" -o "$WORK/deck.json"
"$PY" -c "import json; json.dump({'content': open('$WORK/deck.json').read(), 'name': 'Imported copy'}, open('$WORK/import.json', 'w'))"
step "Import the JSON export" "201, deck #2, identical cards, no unknown cards" \
    POST /api/decks/import "@$WORK/import.json" \
    "{'id': r['deck']['id'], 'source': r['deck']['source'], 'unknown_cards': r['unknown_cards'], 'cards': r['deck']['stats']['card_count']}"

step "Errors share one shape" "404 deck_not_found" GET /api/decks/99 "" "r['error']"
step "Validation errors too" "422 validation_error (lands must be ≤ 99)" \
    POST /api/builds '{"collection": "builtin:expanded", "commander": "Zaxara, the Exemplary", "lands": 150}' "r['error']"
step "Built-in collections are read-only" "409 read_only" DELETE /api/collections/builtin:expanded "" "r['error']['code']"

step "Delete a deck" "204 (empty body)" DELETE /api/decks/2 "" "'(no content)'"

printf '\n\033[32mAPI demo finished.\033[0m  All endpoints: %s/api/docs while a server runs.\n' "$BASE"
