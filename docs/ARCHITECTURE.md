# CommanderAI architecture

```
             ┌──────────────┐          ┌──────────────────────┐
             │  CLI (Typer) │          │ HTTP API (FastAPI)   │◀── web/ (React UI)
             │  cli/        │          │ api/  /api/*         │
             └──────┬───────┘          └──────────┬───────────┘
   ConsoleReporter  │  render errors    Collecting│Reporter, JSON errors
                    ▼                             ▼
        ┌────────────────────────────────────────────────────────┐
        │ services/  — every use-case, no printing, typed I/O    │
        │  build · commanders · collection · analysis · suggest  │
        │  reference · deck_files                                │
        └───────┬───────────────────────┬──────────────────────┬─┘
                ▼                       ▼                      ▼
        deckbuilder/ (scoring,    collection/ (parse,     catalog.py → data/
        slots, mana base, budget, match)                  (oracle JSON, cached
        themes, partner, bracket,                         CardIndex)
        LLM, tokens)              output/ (format, export)
                                                          storage/ → SQLite
                                                          (decks, collections,
                                                          legacy file log)
```

Cross-cutting modules:

| Module | Role |
|---|---|
| `settings.py` | `Settings` (decks dir, default collection, cache dir, DB path, API key, `offline`) resolved from the environment **at call time**; `config.py` keeps the historical import-time constants. `COMMANDERAI_OFFLINE=1` disables every network call (Commander Spellbook, Claude, Scryfall download). |
| `errors.py` | `CommanderAIError` hierarchy. Every user-facing failure has a stable `code`, an HTTP-ish `status_code`, a `message`, optional `details` and `data`. |
| `reporting.py` | `Reporter` / `Notice`. Services report progress steps and notices (`level`, `code`, `message`, `data`) as they happen; every notice is also recorded. |
| `storage/` | SQLite persistence (stdlib `sqlite3`, WAL, one short-lived connection per operation, schema versioned by `PRAGMA user_version`). `DeckRepository`, `CollectionRepository`. Pure storage: no catalog or deck-building logic. |
| `catalog.py` | Parses `oracle_cards.json` once (previously twice per command) and caches the `CardIndex` per file version. Cards are never mutated, so the cache is shared safely. |

## HTTP API (`api/`)

`commanderai serve` runs `api.app.create_app()`: JSON endpoints under `/api`
(contract: [UI_PLAN.md §2](UI_PLAN.md), live docs at `/api/docs`), card images
under `/api/images`, and the built UI (`web/dist`) for every other path.

| Module | Role |
|---|---|
| `app.py` | App factory: error handlers (one JSON error shape), routers, static files, SPA fallback, startup legacy migration |
| `schemas.py` | Request/response models (reusing service models where they are already public shapes) and domain → DTO converters |
| `convert.py` | Build results / stored decks → API shapes (stats, tokens, report, repeatable params) |
| `registry.py` | Collection ids: `builtin:*`, `default`, `stored:N` |
| `state.py` | Application state: settings, image index, build-preview cache (50 entries, 1 h) |
| `images.py` | Card name → local image files (from `image-manifest.json`) |
| `routers/` | `system` (status, vocabulary, card), `collections`, `commanders`, `builds`, `decks` |
| `openapi.py` | `python -m commanderai.api.openapi` prints the schema used to generate the TypeScript types |

## Web UI (`web/`)

React 19 + TypeScript + Mantine 9, built by Vite into `web/dist` and served by
`commanderai serve`.

| Path | Role |
|---|---|
| `src/api/` | `schema.gen.ts` (generated from the OpenAPI schema — never edit), typed `openapi-fetch` client + `ApiError`, TanStack Query hooks (`queries.ts`) with precise cache invalidation |
| `src/state/ActiveCollection.tsx` | The active collection (header selector, remembered in localStorage) |
| `src/lib/` | Pure, unit-tested logic: card filters ⇄ URL, build form ⇄ URL ⇄ request, deck compare, text exports, friendly errors, `useUrlParams` |
| `src/components/` | Card image/tile/detail dialog, mana symbols, color & theme pickers, deck card list, stats charts, build log, tokens, export menu, error boundary |
| `src/pages/` | Collection, Commanders, Build, Decks, Deck detail, Compare, About (each lazy-loaded) |
| `src/theme.ts` | Brand color, accessible colour overrides (WCAG AA), dialog defaults |
| `e2e/` | Playwright flows, screenshots and axe accessibility scans against the real server |

## Service API

All services take a `ServiceContext(settings, reporter)`; the catalog is loaded
lazily on first use (so input errors surface before the catalog load).

| Service | Function | Returns |
|---|---|---|
| build | `build_deck(ctx, BuildRequest)` | `BuildResult`: deck, seed/variety used, theme, quotas + changes, auto-pick info, match report, budget report, bracket report, LLM status, backfill/shortfall, validation errors, notices |
| commanders | `list_commanders(ctx, collection, colors)` | `list[CommanderInfo]` (card, WUBRG colors, rank, partner tags) |
| | `suggest_commanders(ctx, collection, colors=, theme=, top=, variety=, seed=)` | `SuggestCommandersResult` |
| | `auto_select_commander(...)`, `auto_select_partner(...)` | pure helpers |
| collection | `load_collection(ctx, path_or_text, kind=, empty_message=)` | `LoadedCollection` (entries, match, unique cards, `MatchReport`) |
| | `convert_collection(path_or_text)` | `ConvertResult` |
| analysis | `validate_deck_list(ctx, source, commander)` | `ValidationResult` |
| | `deck_tokens(ctx, source)` / `tokens_for_cards(cards)` | `TokensResult` / `list[Token]` |
| | `explain_deck_list(ctx, source, commander)` | `ExplainResult` (LLM) |
| suggest | `suggest_upgrades(ctx, UpgradeRequest)` | `UpgradeResult` |
| reference | `vocabulary()` (+ `archetypes()`, `tribes()`, `aliases()`, `color_groups()`) | `Vocabulary` |
| library | `save_build`, `list_decks`, `get_deck`, `rename_deck`, `delete_deck`, `export_deck(record, fmt)`, `import_deck(ctx, text)`, `parse_deck_text`, `migrate_legacy_decks`, `ensure_legacy_migrated`, `prior_card_lists` | `DeckRecord` / `DeckSummary` |
| collections | `save_collection`, `list_collections`, `get_collection`, `rename_collection`, `replace_collection`, `delete_collection` | `StoredCollection` |
| deck_files | `next_deck_path`, `write_deck_file`, `render_deck` | deck text exports |

Anything that accepts a "source" takes either a `Path` (file) or a `str` (the
raw list text — used for uploads / pasted lists). Build and upgrade requests can
also reference a stored collection with `collection_id`.

## Deck database (`data/commanderai.db`, `COMMANDERAI_DB`)

The database is the **single source of truth** for saved decks; `.txt` files are
exports. Tables:

| Table | Content |
|---|---|
| `decks` | One row per deck: denormalised columns for listing/filtering (name, commander, partner, colors, theme, seed, variety, bracket, budget, card_count, total_price, avg_cmc, source `cli`/`api`/`import`/`legacy`, collection_source, export_path/format, created/updated) + `record`: the JSON `DeckRecord` |
| `collections` | Uploaded collections (name, raw text, line/copy counts) |
| `legacy_imports` | Every `.txt` deck file the library knows, by (path, sha256): `exported` (written by the CLI), `imported`, `failed` |
| `meta` | Key/value flags (e.g. the one-time legacy migration) |

A `DeckRecord` holds a **full snapshot** of the built `Deck` (cards with oracle
text, prices, slots, reasons), the build parameters/report (request, seed,
theme, quotas, budget/bracket reports, notices…), and provenance. A saved deck
therefore never changes when the catalog is refreshed. The same document,
wrapped as `{"format": "commanderai.deck", "version": 1, "deck": {...}}`, is the
JSON export/import format.

**Legacy migration.** On the first use of the deck library, every `decks/*.txt`
file (grouped text, Archidekt, Moxfield, MTGO — all formats 0.7.0 wrote) is
parsed back into a deck and stored with source `legacy` (file mtime kept as the
creation date). Files are tracked by (path, sha256) so nothing is imported twice,
decks deleted from the database are never resurrected from their files, and an
edited file counts as a new deck on the next `decks migrate`.

### Build pipeline (`services/build.py`)

1. resolve options (theme, colors, variety/seed, role quotas)
2. load collection (file check → catalog → parse → match)
3. choose commander(s): explicit, or auto-pick by theme/colors (+ partner)
4. candidate pool (color identity, role classification, scoring)
5. budget filter (budget left after the commanders) → 6. bracket filter
   (Commander Spellbook, or offline rules) → 7. feasibility check
8. non-land picks (heuristic, or LLM with heuristic fallback)
9. backfill / shortfall lands → 10. owned-upgrade swaps
11. mana base → 12. budget enforcement → 13. validation

## Notice codes

Emitted through the reporter (the CLI renders them exactly like the historical
output; the UI can use `data`).

| Code | Level | Data |
|---|---|---|
| `catalog.loaded` | detail | `count` |
| `variety.seed` | detail | `variety`, `seed` |
| `collection.matched` | success | `matched`, `skipped`, `unmatched` |
| `collection.fuzzy` | warning | `original`, `corrected` |
| `collection.unmatched` | error | `name` (only with `verbose`) |
| `commander.auto_selected` | success | `name`, `colors`, `support`, `theme_fit`, `reasons` |
| `partner.auto_selected` | success | `name`, `colors` |
| `partner.tip` | detail | — |
| `commander.selected` | info | `commanders[{name,type_line,oracle_text}]`, `colors` |
| `theme.active` | detail | `theme` |
| `theme.quotas_adjusted` | detail | `changes{slot:[from,to]}` |
| `candidates.found` | detail | `count` |
| `budget.commanders_exceed` | warning | `budget`, `commanders_price` |
| `budget.filtered` | detail | `budget`, `removed` |
| `bracket.offline` | warning | `bracket`, `reason` (offline rules used; combos not checked) |
| `bracket.excluded_cards` | warning | `bracket`, `cards[{name,reason}]` |
| `bracket.excluded_combos` | warning | `combos[{cards,reason}]` |
| `bracket.prioritized` | success | `count` |
| `bracket.remaining` | detail | `count` |
| `candidates.insufficient` | warning | `candidates`, `needed_nonland`, `lands` |
| `candidates.underpowered` | warning | — |
| `picks.heuristic` | detail | — |
| `llm.prior_decks` | detail | `count` |
| `llm.failed` | warning | `error` |
| `picks.backfilled` | detail | `count` |
| `deck.shortfall` | warning | `shortfall`, `deck_size`, `colors` |
| `upgrades.swapped` | success | `count` |
| `budget.swapped` / `budget.met` / `budget.unmet` | success / success / warning | `budget`, `swaps` / `final_price` |
| `deck.validation` | warning | `errors` |
| `explain.started`, `suggest.started` | info | `commander`, … |
| `library.migrated` | success | `count`, `directory`, `decks[{path,id}]` |
| `library.migration_failed` | warning | `path`, `message` |

## Error codes

| Class | `code` | Status |
|---|---|---|
| `InvalidRequestError` | `invalid_request` | 400 |
| `UnknownThemeError` / `UnknownColorsError` | `unknown_theme` / `unknown_colors` | 400 |
| `CollectionNotFoundError` | `collection_not_found` | 404 |
| `CardNotFoundError` | `card_not_found` | 404 |
| `DeckNotFoundError` | `deck_not_found` | 404 |
| `DeckImportError` | `deck_import_failed` | 422 |
| `IllegalCommanderError` / `IllegalPartnerError` | `illegal_commander` / `illegal_partner` | 422 |
| `EmptyCollectionError` / `CollectionTooSmallError` / `InsufficientCardsError` | … | 422 |
| `NoMatchingCommanderError` / `CommanderNotIdentifiedError` | … | 422 |
| `CatalogNotFoundError` | `catalog_not_found` | 503 |
| `LLMError` | `llm_failed` | 503 |

## Verifying behaviour

See [TESTING.md](TESTING.md): `scripts/test.sh` runs the unit tests, lint, the
golden CLI snapshots (current and original-0.7.0-plus-documented-changes) and
the differential test against the original implementation.

## Prices and brackets

- **Prices:** `Card.price_usd` is the single price rule (Scryfall `usd`, else
  `usd_foil`, else `usd_etched`; `None` when unknown). `Deck.total_price` sums all
  100 cards including the commander(s) (unknown = 0; `Deck.unpriced_cards` counts
  them). The budget step, the deck summary, the CLI and the LLM prompt all use it.
- **Brackets** (`deckbuilder/bracket.py`): online, Commander Spellbook's
  `estimate-bracket` decides (commander and partner are sent). Offline — network
  error or `COMMANDERAI_OFFLINE=1` — `check_bracket_offline` applies the same
  per-bracket limits from card data: `Card.game_changer`, extra-turn and
  mass-land-denial text patterns. `BracketResult.mode` is `online`, `offline` or
  `skipped` (bracket 5).
