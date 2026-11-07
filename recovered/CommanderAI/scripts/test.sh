#!/usr/bin/env bash
# Run CommanderAI's test suites and print a PASS/FAIL summary.
#
#   scripts/test.sh            all standard suites (about 6 minutes; no browser tests)
#   scripts/test.sh quick web  what a reviewer needs (about 1 minute)
#   scripts/test.sh quick      unit tests + lint only (about 10 seconds)
#   scripts/test.sh unit       pytest unit/service/library tests
#   scripts/test.sh lint       ruff on the refactored code
#   scripts/test.sh golden     CLI vs tests/golden/expected (current intended behaviour)
#   scripts/test.sh baseline   CLI vs the ORIGINAL 0.7.0 baseline, allowing only
#                              the documented changes in tests/golden/CHANGES.md
#   scripts/test.sh diff       original 0.7.0 CLI vs current CLI with injected fakes
#   scripts/test.sh web        web UI: Biome lint/format, TypeScript, component tests (Vitest)
#   scripts/test.sh e2e        OPTIONAL, heavy: web UI in a real browser (Playwright + Chromium,
#                              ~5 min) against `commanderai serve`; not part of `all`.
#                              Needs a Playwright Chromium (npx playwright install chromium).
#
# Several suites can be given: scripts/test.sh unit golden
# Exit code: 0 if every selected suite passed, 1 otherwise.
set -uo pipefail

cd "$(dirname "$0")/.."
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
    echo "No .venv found — run scripts/setup.sh first." >&2
    exit 2
fi

LOG_DIR="${TMPDIR:-/tmp}/commanderai-test-logs"
mkdir -p "$LOG_DIR"

declare -a NAMES=() RESULTS=() TIMES=()

run_suite() {  # name, description, expected, key-lines regex, command...
    local name="$1" desc="$2" expected="$3" keys="$4"; shift 4
    local log="$LOG_DIR/$name.log" start end status
    printf '\n\033[1m━━ %s\033[0m — %s\n' "$name" "$desc"
    printf '   expected: %s\n' "$expected"
    printf '   log:      %s\n' "$log"
    start=$(date +%s)
    "$@" >"$log" 2>&1
    status=$?
    end=$(date +%s)
    # Show the key result lines (and the end of the log on failure).
    grep -E "$keys" "$log" | sed 's/^/   │ /'
    if [[ $status -ne 0 ]]; then
        echo "   │ ── last lines of the log ──"
        tail -n 25 "$log" | sed 's/^/   │ /'
    fi
    NAMES+=("$name"); TIMES+=("$((end - start))s")
    if [[ $status -eq 0 ]]; then
        RESULTS+=("PASS"); printf '   \033[32mPASS\033[0m (%ss)\n' "$((end - start))"
    else
        RESULTS+=("FAIL"); printf '   \033[31mFAIL\033[0m (%ss) — see %s\n' "$((end - start))" "$log"
    fi
}

suite_unit() {
    run_suite unit "pytest: models, deck builder, services, deck database" \
        "'201 passed, 1 skipped' (the skipped test is the opt-in golden wrapper)" \
        "passed|failed|error" \
        "$PY" -m pytest -q
}
suite_lint() {
    run_suite lint "ruff on the refactored modules" "'All checks passed!'" \
        "All checks passed|Found [0-9]+ error" \
        .venv/bin/ruff check src/commanderai/cli src/commanderai/services src/commanderai/storage \
        src/commanderai/settings.py src/commanderai/errors.py src/commanderai/reporting.py \
        src/commanderai/catalog.py src/commanderai/deckbuilder/budget.py src/commanderai/api \
        scripts tests/test_services.py tests/test_library.py tests/test_fixes.py tests/test_api.py
}
suite_golden() {
    run_suite golden "every CLI case vs tests/golden/expected (byte-for-byte)" \
        "'153/153 cases match'" \
        "cases match|^DIFF|^MISSING" \
        "$PY" scripts/golden.py compare -q
}
suite_baseline() {
    run_suite baseline "CLI vs ORIGINAL 0.7.0 behaviour, only documented changes allowed" \
        "'0 UNEXPECTED differences' (other lines: identical / documented / changed / new)" \
        "^Against|^ +[0-9]+ |^DIFF" \
        "$PY" scripts/golden.py compare --documented -q
}
suite_diff() {
    run_suite diff "original 0.7.0 CLI vs current CLI, partner/bracket/LLM paths via fakes" \
        "'17/17 identical' and every coverage count > 0" \
        "identical$|^DIFF| 0$" \
        "$PY" scripts/difftest.py
}

web_check() {
    (cd web && npm run --silent check:api && echo "API types up to date" && NO_COLOR=1 npx biome check . && npx tsc -b \
        && NO_COLOR=1 npx vitest run && npm run --silent build && npm run --silent check:bundle)
}
suite_web() {
    run_suite web "web UI: API types current, Biome lint + format, TypeScript, Vitest, build, bundle budget" \
        "'API types up to date', 'No fixes applied', 'Tests  46 passed', 'Bundle within budget'" \
        "API types|differ|No fixes applied|Found [0-9]+ (error|warning)|error TS|Tests +[0-9]+|FAIL|initial (JS|CSS)|budget" \
        web_check
}
e2e_run() {
    (cd web && npm run build --silent && npx playwright test)
}
suite_e2e() {
    run_suite e2e "web UI in Chromium at desktop/tablet/phone sizes + WCAG scans (Playwright, real API)" \
        "'77 passed', '58 skipped' — screenshots in web/e2e/screenshots/" \
        "[0-9]+ (passed|failed|flaky|skipped)" \
        e2e_run
}
need_web() {
    if [[ ! -d web/node_modules ]]; then
        echo "web/node_modules missing — run scripts/setup.sh (needs Node.js >= 22.12)." >&2
        exit 2
    fi
}

selected=("$@")
[[ ${#selected[@]} -eq 0 ]] && selected=(all)
for s in "${selected[@]}"; do
    case "$s" in
        all)      need_web; suite_unit; suite_lint; suite_web; suite_golden; suite_baseline; suite_diff ;;
        quick)    suite_unit; suite_lint ;;
        web)      need_web; suite_web ;;
        e2e)      need_web; suite_e2e ;;
        unit)     suite_unit ;;
        lint)     suite_lint ;;
        golden)   suite_golden ;;
        baseline) suite_baseline ;;
        diff)     suite_diff ;;
        *) echo "Unknown suite '$s' (use: all quick unit lint web golden baseline diff e2e)" >&2; exit 2 ;;
    esac
done

printf '\n\033[1mSummary\033[0m\n'
failed=0
for i in "${!NAMES[@]}"; do
    color=32; [[ "${RESULTS[$i]}" == FAIL ]] && { color=31; failed=1; }
    printf '  %-10s \033[%sm%s\033[0m  %s\n' "${NAMES[$i]}" "$color" "${RESULTS[$i]}" "${TIMES[$i]}"
done
exit $failed
