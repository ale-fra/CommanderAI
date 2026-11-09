# Testing CommanderAI

Run these commands from the repository root:

```bash
./scripts/setup.sh
source .venv/bin/activate
./scripts/test.sh
```

Setup requires Python 3.11+, Node.js 22.12+ and Python/npm registry access.
It installs the app plus `dev` and `web` dependencies, creates demo defaults and
builds the UI. The tests themselves use included local data and simulated services;
no API key, personal collection or download of a full card catalog is required.

| Default suite | Checks |
|---|---|
| `unit` | Python tests for models, services, SQLite, API and fixture completeness; zero skipped tests |
| `lint` | Python checks on services, API, scripts and integration tests |
| `diff` | 17 CLI comparisons with the original implementation, using bundled data and simulated external services |
| `web` | API types, Biome, TypeScript, 46 Vitest tests, build and bundle-size limits |
| `smoke` | UI serving, demo collection, legal reproducible 100-card build, SQLite save/read/export/delete |

Each suite prints PASS/FAIL and any failed suite makes the command exit nonzero.
Python tests reject live DNS/TCP access in `tests/conftest.py`; network behavior is
checked through mocked transports. Every test database lives in a temporary directory.

## Included integration data

`tests/fixtures/integration/` contains:

- A 291-card catalog: 194 demo cards, two additional basic lands, five invented
  commanders and 90 invented spells covering the six non-land deck roles.
- Matching CSV/text collections and five synthetic 100-card deck lists.
- Local SVG test images, including both faces of double-faced cards. These are
  test patterns, not card artwork.
- A minimal legacy Zaxara list to test migration independently of golden snapshots.

Invented definitions begin with `Fixture`; the synthetic deck lists are not
commercial Starter Commander deck lists. Tests assert exact counts for these
inputs and fail if required data is missing. `tests/test_fixture_bundle.py` also
checks collection names, quantities and image coverage to catch packaging omissions.
The application still starts with the separate 194-name demo under `data/`.

```bash
./scripts/test.sh quick      # Python tests and lint
./scripts/test.sh diff       # 17 comparisons with injected fakes
./scripts/test.sh web        # UI checks and production build
./scripts/test.sh smoke      # needs web/dist
```

## Optional browser checks

```bash
cd web
npx playwright install chromium
cd ..
./scripts/test.sh e2e
```

Playwright starts `scripts/serve_test_app.py` with the included integration catalog,
collections and test images, plus a fresh database. The optional extra dependency
is a Chromium installation. No external card fixture is needed. Layout-specific
cases intentionally run only on their target desktop/tablet/phone project.

## Historical snapshot comparisons

One historical test is explicitly excluded from the default pytest selection
(`historical` marker); it is not silently skipped for absent integration data.
The original `offline-data/`, `commanderai-sample/` and historical stdout/deck
snapshots were not available in the source repository. Those historical inputs
remain separate from the new fixtures: using new data with old snapshots would
not be a valid comparison.

```bash
python -m pytest -m historical tests/test_golden.py
./scripts/test.sh golden
./scripts/test.sh baseline
```

These opt-in commands fail with an explicit missing-input message until the
matching original inputs and snapshots are restored. Do not capture a baseline
from current behavior and treat it as proof that behavior was preserved.
See `tests/golden/README.md` and `tests/golden/CHANGES.md`.
