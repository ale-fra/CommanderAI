# Reviewer instructions

## 1. Automated checks

Execute these commands in the terminal:

```sh
cd /workspace/CommanderAI
./scripts/setup.sh
source .venv/bin/activate
test -s web/dist/index.html
./scripts/test.sh quick web
```

- `./scripts/setup.sh` creates the Python environment, installs the dependencies,
  configures the bundled offline card data and builds the web UI. It takes about
  1 minute the first time and needs access to the Python and npm package registries.
- `test -s web/dist/index.html` prints nothing and succeeds when the UI was built.

Expected results (the tests take approximately 1 minute in the sandbox):

| Suite | Result | What it checks |
|---|---|---|
| lint | **PASS** | Python code style (ruff) |
| unit | **PASS** | 201 Python tests (deck builder, services, deck database, HTTP API), 1 skipped |
| web | **PASS** | web UI: API types in sync, lint/format, TypeScript, 46 unit tests, production build, bundle-size budget |

The run ends with a summary like this:

```
Summary
  unit       PASS  12s
  lint       PASS  0s
  web        PASS  32s
```

## 2. Manual test of the UI

Run in the terminal:

```sh
./scripts/setup.sh
source .venv/bin/activate
commanderai serve
```

Then open http://localhost:8000.

The React interface loads with a **dark theme** by default; you can switch it by
clicking the selector at the top right (sun/moon icon).

The sidebar menu contains:

- **Collection** — explore all the cards in your collection: search them by name,
  type or rules text, and filter them (color identity, card type, mana value, role,
  rarity, price, commanders only). Click a card to see its details.
- **Commanders** — browse all your eligible commanders (essentially all your
  legendary creatures). Pick one to create a new deck with it: clicking **Build**
  leads to the Build page with that commander already selected.
- **Build** — build your deck by choosing a few options. If you are unfamiliar with
  Commander (Magic: The Gathering), use **Auto-pick** and select the **colors**
  (required), then press **Build deck**. **SAVE your deck** to continue the demo!
- **Decks** — your saved decks appear here: open one to see its cards, statistics,
  tokens and legality, or export it.

## 3. Screenshots

I've also attached a set of screenshots taken locally to simplify the review.
They are in the workspace folder, under **`/workspace/screenshots`**:

| Files | Content |
|---|---|
| `demo-*.png` | A walkthrough: collection, search, commanders, build, stats, decks, about, mobile |
| `<screen>-<desktop\|tablet\|phone>-<dark\|light>.png` | Every screen (collection, card-detail, commanders, build, build-stats, decks, deck-detail, compare, about) at three screen sizes, in both themes |

## Notes

- Everything runs offline on the bundled sample data (500 cards, 27 commanders).
  AI features are not part of this UI.
- Browser end-to-end tests (Playwright) are heavy and are not needed for the review;
  they are optional (`./scripts/test.sh e2e`, requires Chromium).
- More details: `docs/TESTING.md` (all test suites) and `docs/UI_PLAN.md` (UI design).
