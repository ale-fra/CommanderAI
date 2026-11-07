# Changelog

## [Unreleased]

### Added
- React web UI, FastAPI endpoints and SQLite deck/collection services integrated into the main application.
- One-command setup with bundled demo data and a default test suite covering Python, the web UI and API smoke checks.
- API integration tests using the bundled demo catalog; full-catalog regression fixtures remain optional.

### Fixed
- Scryfall downloads accept JSON arrays and gzipped JSONL, preserve the previous cache on failure and support an explicit destination.
- Build collection selection, manual mode with a theme, reproducible rebuilds and repeated commander suggestions.

### Added — web UI (Phase 1)
- **Collection**: card grid/list with images, search, color-identity (within / exactly / including), type, mana value, role, rarity, price and commander filters in the URL; card detail dialog (both faces, prices, owned count, build with this commander); upload with match preview, rename / replace / delete uploaded collections.
- **Commanders**: gallery with supporting-card counts and EDHREC rank, color filter, sorting; ranked suggestions for a theme / colors / variety.
- **Build**: choose a commander (+ legal partner) or auto-pick for a theme/colors; lands, variety + seed, budget, bracket; result with role-grouped cards and reasons, stats charts, tokens, build log and warnings; rebuild, re-roll, save, export.
- **Decks**: library with search, source filter, pagination; deck page with cards, stats, tokens, legality, build info and notes; rename, delete, export downloads, import (JSON or any text list), compare two decks, rebuild with the saved settings.
- Dark theme by default with a light toggle, responsive down to phones, offline fonts and mana symbols, WCAG 2.1 AA (automated axe scans), bundle budget.
- `scripts/demo_ui.sh` guided tour; Playwright suite (flows, screenshots, accessibility).

### Changed (tests)
- `scripts/test.sh` no longer runs the Playwright browser suite by default (too heavy for small sandboxes); it remains available as `scripts/test.sh e2e`. `scripts/test.sh quick web` is the ~1-minute reviewer check. Reviewer guide: `instruction.md`.

### Fixed (found while building the UI)
- Rapid consecutive filter/option changes could lose the first change (URL state).
- The theme picker crashed on the `lifedrain` alias that duplicates an archetype name.

### Added — HTTP API (web UI M1)
- Complete JSON API for the web UI (21 operations): status, vocabulary, card detail; collections (built-in samples and precons, the default collection, uploaded collections: preview, create, rename/replace, delete); commanders, suggestions, legal partners; build previews (`POST /api/builds`, reproducible via the returned seed) and saving them; deck library (list/search/filter/paginate, detail with stats, tokens and validation, rename/notes, delete, export in every format, import).
- One error shape for every failure, request validation included; interactive docs at `/api/docs`.
- Typed web client: `npm run gen:api` generates TypeScript types from the OpenAPI schema; `openapi-fetch` client with `ApiError`; TanStack Query hooks.
- `scripts/demo_api.sh`: guided walkthrough of the API against a throwaway server.
- `Card.rarity`, `Card.set_name`; deck statistics service (mana curve, color pips, roles vs targets, card types).

### Changed
- TypeScript 5.9.3 (instead of 6.0.3) for the web UI: the OpenAPI type generator requires TypeScript 5.x.

### Added — web UI foundation (stack spike)
- `web/`: React 19 + Mantine 9 + Vite 8 + TypeScript 6 + React Router 7 + TanStack Query; dark theme by default with a light toggle; responsive app shell; offline fonts (Inter) and mana symbols (mana-font); Biome, Vitest, Playwright (desktop/tablet/phone screenshots).
- `commanderai serve` (new `web` extra: FastAPI + uvicorn): `/api/status`, `/api/card`, card images, one JSON error shape, and the built UI with client-side routing.
- `scripts/setup.sh` builds the UI when Node.js >= 22.12 is available; `scripts/test.sh web` and `scripts/test.sh e2e`.
- `docs/UI_PLAN.md`: validated stack, API contract, screens, delivery plan.

### Fixed (phase D)
- **`validate`** counts quantities (`15 Plains` = 15), so all five precons validate; checks commander legality and partner pairing; new `--partner/-P`; reports unknown cards.
- **Budget** covers all 100 cards including the commander(s), and one price rule (nonfoil → foil → etched) is used everywhere, so `Budget: deck fits at $X` and `Est. price` agree. Warns when the commander(s) alone exceed the budget.
- **Power brackets offline**: when Commander Spellbook is unreachable the build no longer silently skips the bracket — game changers, extra turns and mass land denial are filtered from local card data (with a notice that combos were not checked). The partner is now sent to Spellbook too.
- **`tokens`**: `Artifact — Food/Treasure/Clue…` instead of `— Food`; `tapped` no longer part of token names; copy tokens listed as `Copy of a permanent`.
- `list decks` card count (fixed by the deck database).

### Added (phase D)
- `COMMANDERAI_OFFLINE=1`: never call external services (set by `scripts/setup.sh` and all test harnesses).
- `Card.game_changer`, `Card.price_usd`, `Deck.unpriced_cards`; `BudgetReport.commanders_price`; `BracketReport.mode`.

### Added — deck database (phase C)
- **SQLite deck database** (`data/commanderai.db`, `COMMANDERAI_DB`) as the single source of truth. `build` stores every deck (full card snapshot + build parameters and report) and still writes the `decks/*.txt` export; it prints the id: `Deck saved → decks/x.txt (deck #N)`.
- **`decks` command group**: `list`, `show`, `export` (json/text/mtgo/moxfield/archidekt), `import` (JSON export or any text decklist), `rename`, `delete`, `migrate`.
- **Legacy migration**: existing `decks/*.txt` files (all formats written by 0.7.0) are imported automatically on first use; tracked by path + hash so nothing is imported twice and deleted decks are not resurrected.
- **Stored collections** (`collections` table and service) for uploaded collections; builds/suggestions accept `collection_id`.
- `scripts/setup.sh` (one-command environment setup), `scripts/test.sh` (all test suites with expected results and a summary), `scripts/check_example.py` (re-test a stored example), `scripts/demo_deck_library.sh` (guided tour), `scripts/difftest.py`, `docs/TESTING.md`, `tests/golden/CHANGES.md`.

### Changed — deck database (phase C)
- `list decks` reads the database (new layout; shows the correct card count of 100).
- LLM anti-repetition reads previous decks from the database.
- `build -f <unknown format>` fails immediately instead of crashing after the build.

### Changed
- **Service-layer refactor of the CLI.** The 1,257-line `cli.py` is now a thin `cli/` package over a new `services/` layer (`build`, `commanders`, `collection`, `analysis`, `suggest`, `reference`, `deck_files`) that returns typed, JSON-serializable results and never prints. Supporting modules: `settings.py` (runtime settings), `errors.py` (typed errors with stable codes), `reporting.py` (structured notices/progress), `catalog.py` (cached catalog). CLI output is unchanged — verified byte-for-byte against 133 golden cases captured from the previous version, plus a differential test of partner/bracket/LLM paths. See `docs/ARCHITECTURE.md`.
- The oracle card file is parsed once per command instead of twice.
- Missing deck/input files and a missing card database now produce a clear error instead of a traceback.

### Added
- `scripts/golden.py` golden-master harness and `tests/golden/baseline/` snapshot.
- Service contract tests (`tests/test_services.py`).
- `COMMANDERAI_DB` setting (default `data/commanderai.db`) reserved for the deck database.

## [0.7.0] - 2026-05-29

### Fixed
- Color identities now display in canonical **WUBRG** order everywhere (e.g. `WUBRG` instead of the alphabetical `BGRUW`) across `list commanders`, `suggest-commanders`, auto-pick, partner output, and warnings.
- **`tokens`/`explain`/`validate` on exported decks** — the collection parser now strips export annotations (Archidekt `[Slot]` tags, Moxfield `*CMDR*`, and `{mana}`/section headers from the text format) before matching. Previously an Archidekt-format deck parsed every card as `"Name [Slot]"` and matched nothing (e.g. `tokens` reported "No token-creating cards"). DFC `Front // Back` names are preserved.

### Added
- **Theme-aware role quotas** — the deck's role split (ramp/draw/removal/wipe/threat/utility) now adapts to `--theme` instead of always targeting the same 10/10/8/4/20/10. Deltas are calibrated against published Commander composition data (The Command Zone "Deckbuilding Template" ep. 658 and commanderdeckmaker.com's "Ratios by Archetype"): e.g. spellslinger ~8 creatures + heavy spells, control 12 removal/6 wipes, aggro tribes ~28 threats with only ~2 wipes, voltron ~22 utility (equipment/auras/protection), aristocrats ~24 threats + 14 sac/payoff utility. Without a theme the split is unchanged. The adjustment is printed (`Role mix adjusted: ...`).
- **`list` command** — `commanderai list [commanders|decks|colors|themes|tribes|aliases|formats|brackets]`. `list commanders` shows every eligible commander in your collection (with color identity, EDHREC rank, and partner ability); the rest show saved decks and the vocabularies accepted by `--theme`, `--colors`, `-f`, and `-b`.
- **Default collection** — `--collection`/`-c` is now optional across `build`, `suggest`, `suggest-commanders`, and `list commanders`, defaulting to `data/my_collection.txt`. A clear error is shown if the file is missing.
- **`list --head N` / `--tail N`** — limit long `list commanders` / `list decks` output.
- **`.env` support + path overrides** — a project-local `.env` is now loaded automatically. `COMMANDERAI_COLLECTION`, `COMMANDERAI_DECKS_DIR`, and `COMMANDERAI_CACHE` override the default collection, decks directory, and cache location (shell environment still wins). See `.env.example`.
- **Partner / two-commander support** — `build` now accepts a second commander via `--partner/-P`. Handles all pairing rules: plain **Partner**, **Partner with X**, restricted **Partner — group**, **Friends forever**, **Choose a Background** + a **Background**, and **Doctor's companion** + a **Time Lord Doctor**. Illegal pairings are rejected with an explanation.
  - Combined color identity (union of both) drives candidate filtering, the mana base, and validation; both commanders' text feeds synergy scoring.
  - Deck math adjusts to 98 cards + 2 commanders = 100; validation, formatter, and all export formats (text/MTGO/Moxfield `*CMDR*`/Archidekt) list both.
  - In auto-pick mode (no `--commander`), if the chosen commander wants a partner, the best-fit owned partner is auto-selected too (respects `--theme`/`--colors`/`--variety`).

## [0.6.0] - 2026-05-29

### Added
- **Auto-pick commander** — `--commander` is now optional on `build`. Omit it and pass `--theme` and/or `--colors` to have CommanderAI choose the best-fit legal commander you own (scored by on-theme card support in its colors, the commander's own theme fit, and EDHREC rank). Respects `--variety` so a seed can surface a different fitting commander.
- **Expanded archetypes** — `--theme` now understands ~35 strategy archetypes (storm, stax, taxes, enchantress, wheels, burn/group-slug, superfriends, vehicles, sagas, blink/ETB, mill, infect, treasure/food/clues, land-destruction, discard, lifedrain, toolbox, pillow-fort, fog, theft, clone, cascade, extra-combat, and more), creature **tribes** (elves, goblins, dragons, slivers, vampires, zombies, ...), and meme/synonym **aliases** (`go-wide`, `bogles`, `tron`, `death-and-taxes`, `8-rack`, `ponza`, ...).
- **Color-combination names** — `--colors` accepts guild/shard/wedge/four-color/five-color names (`azorius`, `jund`, `esper`, `yore-tiller`, `five-color`) in addition to WUBRG letters, on both `build` and `suggest-commanders`.
- **`suggest-commanders --theme`** — rank the commanders you own by how well they fit an archetype.

## [0.5.0] - 2026-05-29

### Added
- **Deck variety** (`--variety 0.0-1.0`, `--seed`) — builds are no longer near-identical on every run. Variety replaces strict top-N selection with seeded, score-weighted sampling across card picks, the mana base, and (in AI mode) shuffled candidate ordering. `--seed` makes any variety build reproducible; passing `--seed` alone implies a moderate variety level. Default (no flags) output is unchanged and deterministic.
- **Theme steering** (`--theme`) — lean a build into an archetype (`aristocrats`, `tokens`, `spellslinger`, `lifegain`, `counters`, `graveyard`, `reanimator`, `blink`, `voltron`, `landfall`, `control`) so the same commander can produce genuinely different decks instead of always the same staples/combo.
- **LLM anti-repetition** — in variety mode, prior saved decks for the same commander are fed to Claude with an instruction to build something meaningfully different.
- **Variety on `suggest-commanders` and `suggest`** — `--variety`/`--seed` now also surface different commander and upgrade suggestions each run (seeded, reproducible), and `suggest` accepts `--theme` to bias recommendations toward an archetype.

### Changed
- In variety mode, scoring emphasizes commander synergy and de-emphasizes raw EDHREC rank, reducing the "same good-stuff pile regardless of commander" effect.

## [0.4.0] - 2026-05-29

### Added
- **Budget cap** (`--budget` USD) — now functional. Caps the deck's total estimated price: candidates priced above the budget are dropped up front, the LLM is told the target, and after assembly the most expensive cards are greedily swapped for cheaper same-slot owned alternatives (non-basic lands downgrade to basics). Reports the final price vs. budget and warns if the pool can't meet it.

## [0.3.0] - 2026-05-29

### Added
- **Power brackets** (`--bracket/-b 1-5`) — controls deck power level using Commander Spellbook API to detect and exclude combos, game changers, extra turns, and mass land denial based on target bracket
  - Bracket 1-2: no game changers, no two-card combos
  - Bracket 3: up to 3 game changers, 1 late-game combo allowed; prioritized cards get score boost
  - Bracket 4-5: no restrictions
  - Bracket-excluded lands (Ancient Tomb, Field of the Dead) also filtered from mana base
- **Token tracking** (`commanderai tokens -d deck.txt`) — lists all tokens a deck can create with P/T, colors, keywords, and which cards produce them
- **Non-legal card detection** — planes, schemes, phenomena, vanguards, and conspiracies from collection exports are now silently skipped instead of reported as errors
- **Upgrade swap refinement** — if LLM suggests upgrades you already own, they get swapped into the deck (replacing backfill cards or strictly weaker picks)

### Fixed
- Fuzzy match cutoff raised from 0.85 → 0.90 to prevent garbage matches ("Contract" → "Contradict", "Ood Sphere" → "Wooden Sphere")
- Cards like "Contract", "Spirit" that exist in Scryfall as non-Commander-legal are now detected before fuzzy matching runs
- Upgrade suggestions no longer recommend cards you already own
- Bracket-excluded lands no longer sneak into mana base via separate land picker path

## [0.2.0] - 2026-05-28

### Added
- **Deck explanation** (`commanderai explain -d deck.txt`) — AI breakdown of strategy, synergies, win conditions
- **Upgrade suggestions** (`commanderai suggest`) — recommends cards to buy with direct synergy detection (transform enablers, creature type references, keyword matches)
- **Collection converter** (`commanderai convert`) — Archidekt/CSV to text format with aggregation
- **Auto-naming** — deck files auto-save to `decks/` with counter (`atraxa.txt`, `atraxa_2.txt`, ...)
- **Small collection handling** — warns on <100 cards, backfills with basics when pool is thin
- **Token/special card detection** in collection matching — single-word names, DFC substitutes skipped

### Fixed
- Off-color lands in mono-colored decks (mana_base now filters by color identity)
- LLM returning <99 cards (backfill from heuristic + extra basics)
- Comment lines triggering CSV format detection
- Regex error in synergy scoring (`+1/+1 counter` pattern)

## [0.1.0] - 2026-05-28

### Added
- Initial release
- `commanderai build` — build Commander deck from collection (heuristic or AI)
- `commanderai suggest-commanders` — find best commanders in your collection
- `commanderai update-data` — download Scryfall bulk data
- `commanderai validate` — check deck legality
- `commanderai export` — export to text/MTGO/Moxfield/Archidekt formats
- Scryfall bulk data integration with local caching
- EDHREC rank + keyword synergy + CMC curve scoring
- Slot classification (ramp/draw/removal/wipe/threat/utility)
- Proportional mana base with dual/fetch priority
- Claude Sonnet integration for intelligent card selection
