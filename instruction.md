# Run CommanderAI

From the repository root:

```bash
./scripts/setup.sh
source .venv/bin/activate
./scripts/test.sh
commanderai serve
```

Open http://localhost:8000. Setup builds the React UI and configures the bundled
demo collection; an existing `.env` is preserved. The initial install requires
Python/npm registry access. The demo then works offline.

The default test summary should show `unit`, `lint`, `web` and `smoke` as PASS.
Some larger regression tests are skipped because their optional full-catalog
fixtures are not bundled. See [docs/TESTING.md](docs/TESTING.md).

The interface starts with a dark theme; the header switches to the light theme.
Use Collection to search/filter cards or upload a collection, Commanders to choose
a commander, Build to generate and save a deck, and Decks to manage and compare
saved decks. The sample supports Zaxara, the Exemplary. Card images are not bundled;
placeholders are expected until you configure a local image manifest and files.
