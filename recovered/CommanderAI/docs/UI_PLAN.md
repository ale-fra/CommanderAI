# Web UI — Phase 1 plan

Status: **Phase 1 delivered (M0–M6).** See §6 for decisions taken during implementation.

Scope (Phase 1): Collection, Commanders, Deck Builder, Deck Library. AI features
(Claude build / explain / upgrade suggestions) are hidden. English only.

## 1. Stack (validated)

| Layer | Choice | Version (pinned) | Notes from the spike |
|---|---|---|---|
| Runtime | Node.js | **≥ 22.12** (build only) | Node 20 is end-of-life; Vite 8 / Vitest 5 need ≥ 22.12 |
| Build | Vite + @vitejs/plugin-react | 8.3.5 / 6.1.2 | production build 3 s; JS 146 kB gzip, CSS 45 kB gzip |
| Language | TypeScript | **5.9.3** | 6.0 was tried in the spike, but the type generator (`openapi-typescript`) requires TypeScript 5.x; 7.0 (native compiler) has a single release so far |
| API types | openapi-typescript + openapi-fetch | 7.13.0 / 0.17.0 | `npm run gen:api`: FastAPI schema → `web/openapi.json` → `src/api/schema.gen.ts` |
| UI kit | Mantine (core, hooks; later form, charts, notifications) | 9.7.3 | API as expected (AppShell, color-scheme manager, responsive props) |
| Routing | React Router (declarative mode) | **7.18.4** | v8 requires Node ≥ 22.22 → kept v7 (maintained) |
| Server state | TanStack Query | 5.104.5 | |
| Icons / symbols | Tabler icons; mana-font (MIT CSS, OFL font) | 3.49.0 / 1.18.0 | bundled `woff2`/`woff` only; the unlicensed **MPlantin** face and unused formats are stripped at build time |
| Font | Inter (@fontsource-variable) | 5.3.0 | offline |
| Lint/format | Biome | 2.6.2 | ⚠ `biome migrate` turned `recommended` into `preset: none` (all rules off) — fixed to `preset: recommended` |
| Unit tests | Vitest + Testing Library + jsdom | 5.0.5 / 16.3.3 | |
| E2E | Playwright (+ preinstalled Chromium) | 1.56.1 | desktop 1440×900, tablet 834×1112, phone Pixel 7 |
| API | FastAPI + uvicorn (`web` extra) | 0.162 / 0.54 | `commanderai serve` serves `/api` + the built UI |

Spike findings that shape the design:
- Card names contain `/` (`Invasion of Zendikar // Awakened Skyclave`) → names
  travel in **query strings**, never path segments.
- Narrow screens: a mana cost on the same line as the name truncates the name →
  cost goes on its own line below `sm`.
- Light theme: the brand accent needs a darker shade for contrast.

## 2. API contract

Conventions: JSON; `snake_case` fields; every error is
`{"error": {"code", "message", "details": [], "data": {}}}` with the status of the
domain error (400 invalid input, 404 not found, 409 read-only, 410 gone, 422
rule/data problem, 503 unavailable); request-validation errors use code
`validation_error`. Interactive documentation: `/api/docs`.
TypeScript types are **generated from the OpenAPI schema** and committed:
`tests/test_api.py` fails if `web/openapi.json` is stale, and `npm run check:api`
(part of `scripts/test.sh web`) fails if `schema.gen.ts` doesn't match it.

### Collection ids
| Id | Source |
|---|---|
| `builtin:expanded` | `commanderai-sample/expanded-collection.txt` (796 cards) |
| `builtin:sample` | `commanderai-sample/sample-collection.txt` (296 cards) |
| `builtin:precon:<slug>` | `commanderai-sample/precons/<slug>.txt` (titles from `sources.json`) |
| `default` | `COMMANDERAI_COLLECTION`, if it exists and isn't one of the above |
| `stored:<n>` | uploaded collection in the database |

### Endpoints

| Method & path | Purpose | Body / query → response |
|---|---|---|
| `GET /api/status` | header badge, About page | → version, offline, catalog (cards, snapshot date), database (decks, collections), default collection id, legacy-migration summary |
| `GET /api/vocabulary` | pickers | → colors (grouped), archetypes (+quota deltas), tribes, aliases, formats, brackets |
| `GET /api/card?name=` | card detail | → `CardDetail` (summary + faces, all prices, set, legal roles) |
| `GET /api/collections` | collection selector | → `CollectionInfo[]` (id, kind, name, description, entries, copies) |
| `GET /api/collections/{id}` | match report | → `CollectionInfo` + `MatchReport` (fuzzy, unmatched, skipped) |
| `GET /api/collections/{id}/cards` | collection grid | → `CollectionCard[]` (all owned cards + quantity; filtered client-side) |
| `POST /api/collections/preview` | upload dialog | `{content}` → `MatchReport` + counts (nothing saved) |
| `POST /api/collections` | upload | `{name, content}` → `CollectionInfo` (201) |
| `PATCH /api/collections/{id}` | rename / replace (stored only) | `{name?, content?}` → `CollectionInfo` |
| `DELETE /api/collections/{id}` | delete (stored only) | → 204 |
| `GET /api/commanders?collection=&colors=` | commander gallery | → `CommanderEntry[]` (card, colors, rank, partner tags, can_take_partner, supporting cards) |
| `GET /api/commanders/suggestions?collection=&theme=&colors=&top=&variety=&seed=` | ranked suggestions | → suggestions with support, fit, score, seed used |
| `GET /api/commanders/partners?collection=&commander=` | builder partner picker | → owned cards that can legally pair |
| `POST /api/builds` | build preview (not saved) | `BuildParams` (collection, commander?, partner?, theme?, colors?, lands, variety, seed?, budget?, bracket?) → `{build_id, expires_at, result: {params (seed resolved), deck, stats, tokens, report}}` |
| `POST /api/decks` | save a previewed build | `{build_id, name?}` → `DeckDetail` (201); **410** if the preview expired |
| `GET /api/decks?commander=&source=&q=&limit=&offset=` | library | → `{total, items: DeckSummary[]}` |
| `GET /api/decks/{id}` | deck page | → `DeckDetail` |
| `PATCH /api/decks/{id}` | rename / notes | `{name?, notes?}` → `DeckDetail` |
| `DELETE /api/decks/{id}` | delete | → 204 |
| `GET /api/decks/{id}/export?format=` | download | json / text / mtgo / moxfield / archidekt, with `Content-Disposition` |
| `POST /api/decks/import` | import | `{content, name?, filename?}` → `{deck: DeckDetail, unknown_cards}` |
| `GET /api/images/{file}` | card images | JPEG, cached for a year (immutable) |

Key shapes:
- **`CardSummary`**: name, mana_cost, cmc, type_line, oracle_text, colors,
  color_identity, keywords, power/toughness, rarity, edhrec_rank, price_usd (null =
  unknown), game_changer, role (RAMP…LAND), is_commander, partner_tags,
  images {front, back}.
- **`BuildResult`**: `params` (what was requested, with the seed actually used —
  sending them again reproduces the deck), `deck` (commander/partner + 98–99 cards
  with slot and reason), `stats`, `tokens`, and `report`: theme, color filter,
  variety + seed, lands, quotas and the theme's changes, auto-pick info, match
  report, budget report, bracket report (mode online/offline, exclusions),
  backfill/shortfall, validation errors, **notices** (the build log).
- **`DeckStats`**: card_count, total_price, unpriced_cards, avg_cmc, mana_curve
  (0…7+), color_pips (W U B R G), roles vs role targets, card types, land count.
- **`DeckDetail`**: id, name, source, created/updated, notes, export file, deck,
  stats, tokens, validation errors, `report` (null for imports / legacy decks) and
  `params` — set whenever the build can be repeated from the UI (UI builds, and CLI
  builds made from a known collection).

Build previews are kept in memory (last 50, 1 hour). Builds are deterministic, so
"rebuild" with the returned seed reproduces an expired preview.

## 3. Screens

Global: header (logo, **active collection selector**, offline badge, theme
toggle); navigation Collection · Commanders · Build · Decks · About (sidebar ≥
`sm`, burger drawer on phones). The active collection is remembered in
localStorage; every page uses it. Filters and builder options live in the URL.

### Collection (`/collection`)
- Summary: cards, copies, color-identity distribution, match report (fuzzy /
  unmatched / skipped) when relevant.
- Toolbar: search (name + rules text), color identity (WUBRG toggles: *within* /
  *exactly* / *including*), type, mana value range, rarity, role, theme, max price,
  commanders only; sort (name, mana value, price, EDHREC); grid ⇄ list.
- Grid: card images, virtualised (2 / 3–4 / 5–6 columns); list: name, cost, type,
  role, price, quantity.
- Card detail: modal on desktop, full-screen sheet on phones: image (flip for
  double-faced cards), rules text, prices, EDHREC rank, role, game-changer flag,
  "Build with this commander" for commanders.
- Manage collections: upload (paste or file; CSV or text) → preview match report
  → save; rename / replace / delete stored ones.

### Commanders (`/commanders`)
- Gallery of eligible commanders: image, color identity, EDHREC rank, partner
  tags, supporting cards; color filter; sort.
- "Suggest" panel: theme, colors, how many, variety + seed → ranked list with
  supporting cards and theme fit.
- Every commander: **Build** → `/build?commander=…`.

### Build (`/build`)
- Options: mode *Choose commander* (searchable commander picker, partner picker
  shown only when the commander can pair) or *Auto-pick* (theme and/or colors);
  theme (grouped: archetypes / tribes / aliases, showing the role-mix change);
  colors (WUBRG toggles + guild/shard names); lands (slider 30–42); variety slider
  + seed (lock / re-roll); budget ($); bracket 1–5 with descriptions and the
  "offline rules" note.
- Result: commander(s), 100 cards, price (+ unpriced count), average mana value;
  tabs **Cards** (grouped by role, grid/list, pick reason), **Stats** (mana curve,
  color pips, roles vs targets, types), **Tokens**, **Log** (notices; bracket
  exclusions; budget report; auto-pick reasons).
- Actions: **Save** (name) → deck page; **Rebuild** (same seed); **Re-roll** (new
  seed); **Export** (copy / download any format).
- Desktop: options | result side by side. Phone: options, then result tabs.

### Decks (`/decks`, `/decks/:id`)
- Library: name, commander thumbnail, colors, cards, price, source (CLI / UI /
  import / legacy), created; search, filter by commander / source, sort.
- Actions: open, rename, delete (confirm), export, **Import** (JSON export or any
  text decklist; unknown cards reported), **Compare** two decks (added / removed /
  shared, by role).
- Deck page: header + tabs Cards · Stats · Tokens · Validation · Build info
  (parameters + log); "Rebuild with these settings" → `/build?…`.

### About (`/`)
Catalog snapshot, offline mode, database location, counts, versions.

States everywhere: loading skeletons, empty states with a next step, errors
mapped from the API `code` (e.g. `collection_too_small` → "Pick a larger
collection"), toasts for saves/deletes.

## 4. Quality bar
- Responsive from 360 px; touch targets ≥ 44 px; desktop hover previews, tap on
  touch devices.
- WCAG 2.1 AA: keyboard navigation, visible focus, contrast in both themes,
  mana symbols with text labels, `prefers-reduced-motion`.
- Performance: initial JS ≤ 300 kB gzip; lazy images; virtualised grids.

## 5. Delivery plan

| Step | Content | Verification (scripts) |
|---|---|---|
| M0 ✅ | Stack spike, typed client pipeline (`gen:api`, `unwrap`, query hooks) | `scripts/test.sh web e2e` |
| M1 ✅ | API: all endpoints + DTOs, build-preview cache, OpenAPI → TypeScript types | `tests/test_api.py` (43 tests), `scripts/demo_api.sh`, OpenAPI types up to date |
| M2 ✅ | Shell, collection selector, Collection page, card detail, uploads | `e2e/collection.spec.ts` + screenshots (3 sizes × 2 themes) |
| M3 ✅ | Commanders page | `e2e/commanders.spec.ts` |
| M4 ✅ | Build page | `e2e/build.spec.ts`: build / tabs / rebuild / re-roll / save / auto-pick / budget + bracket / errors / deep links / phone layout |
| M5 ✅ | Decks library, deck page, import/export, compare | `e2e/decks.spec.ts` |
| M6 ✅ | Accessibility, performance, polish, docs | `e2e/a11y.spec.ts` (axe WCAG 2.1 A/AA, both themes, desktop + phone), bundle budget, `scripts/demo_ui.sh` |

Each step ends with `scripts/test.sh` green, reviewed screenshots, and a
`scripts/demo_ui.sh` section describing what to click and what you should see.

## 6. Decisions taken during implementation

- **Routes:** `/` opens the Collection (the natural starting point); About moved to
  `/about`. Compare is `/decks/compare?a=&b=`.
- **Large lists:** progressive rendering (60 cards at a time, more as you scroll,
  native lazy images) instead of list virtualisation — simpler with a responsive
  grid and fast enough for collections of this size.
- **Collection filters:** search, color identity (within / exactly / including),
  type, mana value, role, rarity, max price, commanders only. The theme filter was
  left to the Commanders and Build screens (theme matching is server-side logic).
- **URL state:** filters and build options live in the URL. Updates are merged
  into `window.location` (`useUrlParams`), because React Router's functional
  updater sees the previous render — two quick clicks used to lose the first.
- **Build previews** are exported in the browser (Moxfield / Archidekt / MTGO
  text); saved decks are exported by the API (all formats, downloads).
- **Build button** is truly disabled while the form is incomplete, with the reason
  shown under it. On phones the options collapse after a build and the page
  scrolls to the result.
- **Error boundary** around pages: a crash in one screen shows a message and a
  reload button instead of a blank app.
- **Accessibility:** Mantine's default secondary text and light-variant badge
  colours fail WCAG AA contrast; the theme overrides them (dimmed text ≈ 6:1,
  light-variant text darkened per colour). Charts are hidden from assistive
  technology and duplicated as text. Icon-only buttons and slider thumbs have
  accessible names; card tiles are named by their visible content.
- **Performance budget:** initial JS ≤ 300 kB gzip, CSS ≤ 80 kB (checked by
  `npm run check:bundle`; currently ≈ 187 kB and 47 kB). Pages and charts are
  loaded on demand.
- **API:** theme role-target changes are `{before, after}` objects (tuples don't
  survive the generated client types).
