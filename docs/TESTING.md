# Testing CommanderAI

Run these commands from the repository root:

```bash
./scripts/setup.sh
source .venv/bin/activate
./scripts/test.sh
```

Setup requires Python 3.11+, Node.js 22.12+ and access to Python/npm package
registries. It creates `.venv`, installs the app and development dependencies,
configures the bundled demo data when `.env` does not exist, and builds `web/dist`.
An existing `.env` is preserved. After setup, the default checks run offline.

The default run prints a PASS/FAIL summary and exits nonzero if any selected suite
fails:

| Suite | Checks |
|---|---|
| `unit` | Python deck-building, storage and API tests; optional fixture-dependent cases are skipped when their data is absent |
| `lint` | Python checks on application services, API, scripts and integration tests |
| `web` | API type synchronization, Biome, TypeScript, 46 Vitest tests, production build and bundle-size limits |
| `smoke` | Built React UI served by FastAPI, demo collection, legal 100-card build, reproducible seed, SQLite save/read, JSON export and delete |

The bundled-data API tests are in `tests/test_api_demo.py`. They use isolated
SQLite databases and the 194-name demo collection. `scripts/verify_ui.py` also
uses a temporary database and never writes to your deck library.

For shorter checks:

```bash
./scripts/test.sh quick      # Python tests and lint
./scripts/test.sh web        # UI checks and production build
./scripts/test.sh smoke      # requires an existing web/dist build
./scripts/test.sh unit web   # combine suites
```

## Optional full-catalog regression fixtures

The larger tests in `tests/test_services.py`, `tests/test_library.py`, parts of
`tests/test_fixes.py`, and the fixture-based contract tests in `tests/test_api.py`
expect an additional `offline-data/oracle_cards.json` and files under
`commanderai-sample/`. They are skipped when the required fixtures are not
installed. The API contract snapshot and bundled-data API tests still run.

Golden comparisons additionally require saved outputs in
`tests/golden/baseline/` or `tests/golden/expected/`. The scripts remain available:

```bash
./scripts/test.sh golden     # current CLI versus saved expected outputs
./scripts/test.sh baseline   # documented differences versus the original CLI
./scripts/test.sh diff       # differential checks with injected card data
```

These optional suites are outside the default run. Do not generate a baseline
from changed behavior and treat it as evidence that the behavior is unchanged.
See `tests/golden/README.md` and `tests/golden/CHANGES.md` for the comparison rules.

## Optional browser tests

```bash
cd web
npx playwright install chromium
cd ..
./scripts/test.sh e2e
```

The browser suite uses the full-catalog fixtures described above and a temporary
deck database. It runs Chromium at desktop, tablet and phone sizes, exercises
screen flows and checks accessibility. It is optional because it requires those
fixtures plus a browser installation. Screenshots go in `web/e2e/screenshots/`.

The UI state regression tests also run in the lightweight Vitest suite: manual
mode with a selected theme, switching the active collection, rebuilding from
resolved parameters, saved build links and repeated suggestion requests.
