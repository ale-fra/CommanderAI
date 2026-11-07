# Testing CommanderAI

Everything below runs offline against the bundled catalog (`offline-data/`) and
sample collections. No API key and no network access are needed; the test
harnesses set `COMMANDERAI_OFFLINE=1` so results are identical on machines that
do have network access.

## 1. One-time setup

```sh
scripts/setup.sh              # creates .venv, installs CommanderAI + pytest + ruff,
                              # writes .env (offline catalog), runs a smoke test
scripts/setup.sh --recreate   # same, from a fresh .venv
```

Expected ending:

```
==> Smoke test: commanderai list commanders --head 3
Eligible commanders (27): (showing first 3 of 27)
  Syr Konrad, the Grim [B] EDHREC #266
  ...
Setup complete.
```

Then either `source .venv/bin/activate` and use `commanderai ...`, or call
`.venv/bin/commanderai ...` directly. Python 3.11+ is required
(`PYTHON=/path/to/python3.12 scripts/setup.sh` to pick an interpreter).

## 2. Run the tests

```sh
scripts/test.sh quick web    # what a reviewer needs: unit + lint + web UI, ~1 minute
scripts/test.sh              # all standard suites (no browser tests), ~6 minutes
scripts/test.sh quick        # unit + lint, ~10 seconds — use while developing
scripts/test.sh e2e          # OPTIONAL and heavy: browser tests (Playwright + Chromium), ~5 minutes
scripts/test.sh golden diff  # any combination of suites
```

| Suite | What it proves | Time | Expected result |
|---|---|---|---|
| `unit` | Models, deck builder, service layer, deck database, HTTP API (pytest) | ~5 s | `201 passed, 1 skipped` (the skipped one is the opt-in golden wrapper) |
| `lint` | `ruff` on all refactored/new modules | ~1 s | `All checks passed!` |
| `golden` | Every CLI case (153) matches `tests/golden/expected/` byte-for-byte: console output, exit codes, written deck files, and the deck-database contents | ~3 min | `153/153 cases match` |
| `baseline` | The CLI still behaves like the **original 0.7.0**: compared with `tests/golden/baseline/`, only the changes documented in `tests/golden/CHANGES.md` are accepted | ~3 min | `0 UNEXPECTED differences` |
| `web` | Web UI: generated API types up to date, Biome lint + format, TypeScript, Vitest (filters, build form, compare, exports, errors, theme contrast, mana symbols), production build, bundle budget | ~30 s | `API types up to date`, `No fixes applied`, `Tests  46 passed`, `Bundle within budget` |
| `e2e` *(optional, not in `all`)* | Web UI in Chromium at desktop / tablet / phone sizes against the real `commanderai serve` (rebuilds `web/dist` first): every screen's flows, screenshots (`web/e2e/screenshots/`), and axe WCAG 2.1 A/AA scans in both themes | ~5 min | `77 passed`, `58 skipped` (functional flows run once, on desktop) |
| `diff` | The original 0.7.0 `cli.py` and the current CLI, run side by side with identical fakes for paths the offline data can't reach (partners, Commander Spellbook, Claude) | ~10 s | `17/17 identical`, every coverage count > 0 |

Expected summary of `scripts/test.sh`:

```
Summary
  unit       PASS  5s
  lint       PASS  1s
  web        PASS  8s
  golden     PASS  200s
  baseline   PASS  195s
  diff       PASS  13s
```

The browser suite (`e2e`) is not part of the default run: it needs a Playwright
Chromium (`cd web && npx playwright install chromium`) and is too heavy for small
sandboxes. Run it explicitly with `scripts/test.sh e2e`.

The full output of every suite is saved in `/tmp/commanderai-test-logs/<suite>.log`.

### Reading the `baseline` report

```
Against tests/golden/baseline:
    42 identical                                  ← byte-for-byte as in 0.7.0
    74 identical apart from documented changes    ← e.g. only the '(deck #N)' suffix or a
                                                     masked price differs; all else verified
    17 changed by a documented change             ← a fix legitimately changes the result
                                                     (validate, budget picks, brackets, tokens)
    20 new cases (no baseline)                    ← features/fixes that did not exist in 0.7.0
     0 UNEXPECTED differences                     ← must be 0
```

`scripts/golden.py changes` lists every documented change and the cases it may
affect; `tests/golden/CHANGES.md` explains each one with examples.

Any `DIFF` line shows a unified diff (`-` = 0.7.0, `+` = now). Run a single
case with `.venv/bin/python scripts/golden.py compare --documented -k <case-name>`.

### HTTP API by hand

```sh
scripts/demo_api.sh          # starts a throwaway server and walks through every endpoint group
```

Each of the 17 steps prints the request, what you should see and the actual
response (HTTP status + summary): status, collections, card detail, commanders,
upload preview, build → save → list → rename → export → import, and the error
shapes (404 / 422 / 409). While any server runs, `/api/docs` is the interactive
API documentation.

### Web UI by hand

```sh
scripts/demo_ui.sh           # throwaway instance + a screen-by-screen checklist of what to click and see
scripts/demo_ui.sh --mine    # same checklist on your own data
commanderai serve            # just run it: http://127.0.0.1:8000 (API docs: /api/docs)
```

During development, run the UI with hot reload next to the API:
`commanderai serve` in one terminal and `cd web && npm run dev` in another
(http://127.0.0.1:5173, `/api` is forwarded to port 8000).

## 3. Re-test your own stored example

If you saved a deck (and optionally its console output) from an earlier
version, rebuild it with the same arguments and compare:

```sh
.venv/bin/python scripts/check_example.py <stored-deck-file> [--log <stored-console-log>] \
    -- <the same arguments you gave to `commanderai build`>

# example
.venv/bin/python scripts/check_example.py ~/saved/zaxara__the_exemplary.txt \
    -- -C "Zaxara, the Exemplary" --no-llm
```

Expected:

```
Running: commanderai build -C Zaxara, the Exemplary --no-llm
Exit code: 0

Deck file: IDENTICAL
Console output: IDENTICAL          (only with --log)
```

- The deck file must be identical. The console log is compared after ignoring
  spinner lines, the new `(deck #N)` suffix and the directory of the saved file.
- The build runs against the bundled sample collection unless your arguments
  contain `-c <collection>`; it never touches your own `decks/` or database.
- `--variety` without `--seed` is random by design and can't be reproduced.
- Examples built with `--budget` or `--bracket 1-4` before the phase-D fixes can
  legitimately differ (commander now counted in the budget; brackets enforced
  offline) — see `tests/golden/CHANGES.md` D2/D3.
- Console wrapping depends on terminal width: pass `--columns 80` if your log was
  captured by piping (`| tee`), which uses 80 columns.

## 4. Try the deck database by hand

```sh
scripts/demo_deck_library.sh          # guided tour in a throwaway directory
scripts/demo_deck_library.sh --keep   # keep the directory to inspect demo.db
```

Each step prints the command, what you should see, and the actual output:
legacy `.txt` migration → build (stored + exported) → list → show → export
JSON/Moxfield → import → rename/delete → migrate again (nothing resurrected) →
friendly errors.

## 5. See the bug fixes before/after

```sh
scripts/demo_fixes.sh
```

For each phase-D fix (D1–D6) it prints the 0.7.0 output (from
`tests/golden/baseline/`) next to the live output of the current code, with
what to expect — e.g. all five precons now `Deck is valid! (100 cards)`, the
budget line equal to `Est. price`, bracket 2 excluding Rhystic Study and
Mystical Tutor offline, `Artifact — Food` in the token list.

## 6. When behaviour changes on purpose

1. Implement the change and its unit tests.
2. `scripts/test.sh baseline` shows the new differences. Add a
   `DocumentedChange` to `scripts/golden.py` (a rewrite rule and/or the
   superseded cases) and describe it in `tests/golden/CHANGES.md`, until the
   report shows `0 UNEXPECTED differences`.
3. Re-capture the current expectation:
   `.venv/bin/python scripts/golden.py capture --dest tests/golden/expected`
4. `scripts/test.sh` must be all PASS.

`tests/golden/baseline/` is never regenerated (the harness refuses to overwrite it).
