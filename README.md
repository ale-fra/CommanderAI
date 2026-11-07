# CommanderAI

AI-powered Magic: The Gathering Commander deck builder that works with **your actual collection**. No more browsing decklists you can't build — get a playable 100-card deck from cards you already own.

## Web UI

```bash
scripts/setup.sh          # Python 3.11+ and Node.js >= 22.12
source .venv/bin/activate
commanderai serve         # → http://127.0.0.1:8000
```

- **Collection** — browse your cards (images, search, color identity / type / mana
  value / role / rarity / price filters), card details, upload and manage collections.
- **Commanders** — every commander you own, with supporting-card counts; suggestions
  for a theme or colors.
- **Build** — pick a commander or let CommanderAI choose one for a theme/colors;
  lands, variety + seed, budget, power bracket; the result with stats, tokens and the
  build log; rebuild, re-roll, save, export.
- **Decks** — your library: search, rename, notes, legality, export/import, compare
  two decks, rebuild with the same settings.

Dark theme by default, with a light toggle and responsive layouts for phones.
After setup, the bundled demo collection and card catalog work offline. The demo
contains 194 distinct card names; card images are not bundled, so placeholders are
shown until a local image manifest and its files are configured. Upload your own
collection from the Collection page.

Run `scripts/test.sh` for Python tests, lint, UI tests/build and the API smoke test.
See [docs/TESTING.md](docs/TESTING.md) for optional full-catalog and browser checks.

## What it does

- **Builds decks** from your collection using heuristic scoring + optional AI (Claude) for smarter picks
- **Suggests commanders** from cards you own, ranked by how many supporting cards you have
- **Suggests upgrades** — cards to buy that synergize with your commander
- **Explains decks** — AI breakdown of strategy, synergies, and how to play
- **Lists tokens** — shows all tokens your deck can create (so you can grab the right token cards)
- **Exports** to Moxfield, Archidekt, MTGO formats

## Quick Start

```bash
# Install (creates .venv, installs everything, configures the bundled demo data)
scripts/setup.sh
source .venv/bin/activate

# …or manually
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Optional: download the full card catalog into a separate cache.
COMMANDERAI_OFFLINE=0 COMMANDERAI_CACHE=~/.commanderai commanderai update-data
# Update .env to use ~/.commanderai, then import your own collection.

# Import your collection from Archidekt CSV export
commanderai convert -i ~/Downloads/archidekt-collection-export.csv -o data/my_collection.txt

# Build a deck (heuristic — free, no API key needed)
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice" --no-llm

# Build with AI (smarter picks + explanations)
export ANTHROPIC_API_KEY=YOUR_API_KEY_HERE
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice"
```

## Commands

| Command | Description |
|---------|-------------|
| `build` | Build a Commander deck from your collection |
| `suggest-commanders` | Find the best commanders in your collection |
| `suggest` | Recommend cards to buy for a specific commander |
| `explain` | AI explanation of a deck's strategy and synergies |
| `tokens` | List all tokens a deck can create |
| `convert` | Convert Archidekt/CSV export to simple text format |
| `update-data` | Download/refresh Scryfall card database |
| `validate` | Check a deck for Commander legality (size with quantities, color identity, singleton, commander/partner legality) |
| `list` | List eligible commanders, saved decks, or the colors/themes/tribes/aliases/formats/brackets vocabularies |
| `decks` | Deck database: `list`, `show`, `export`, `import`, `rename`, `delete`, `migrate` |
| `serve` | Start the web UI and HTTP API at http://127.0.0.1:8000 (needs the `web` extra; the UI is built by `scripts/setup.sh`) |

> `--collection`/`-c` is optional for `build`, `suggest`, `suggest-commanders`, and `list commanders` — it defaults to `data/my_collection.txt`.

```bash
commanderai list commanders                 # every eligible commander you own
commanderai list commanders --colors jund --head 20   # top 20 in Jund
commanderai list decks --tail 5             # 5 most recent saved decks
```

### Configuration (`.env`)

The setup script creates `.env` with demo defaults. You can edit it or start from `.env.example`:

```bash
ANTHROPIC_API_KEY=YOUR_API_KEY_HERE
# COMMANDERAI_COLLECTION=data/my_collection.txt   # default collection file
# COMMANDERAI_DECKS_DIR=decks                     # where decks are saved
# COMMANDERAI_CACHE=~/.commanderai                # Scryfall cache location
# COMMANDERAI_DB=data/commanderai.db              # deck database
# COMMANDERAI_OFFLINE=1                           # never call external services
```

Shell environment variables take precedence over `.env`.

## Build Options

```bash
commanderai build \
  -c data/my_collection.txt \    # Your collection file
  -C "Commander Name" \          # Commander to build around
  --no-llm \                     # Skip AI (free, fast)
  --lands 35 \                   # Adjust land count
  --budget 50 \                  # Max deck price (USD, all 100 cards incl. commander)
  --bracket 2 \                  # Power bracket 1-5 (see below)
  --variety 0.6 \                # 0=deterministic, higher=more variation between builds
  --seed 42 \                    # Reproducible variety (implies --variety if unset)
  --theme aristocrats \          # Lean into an archetype (see below)
  -f archidekt \                 # Export format: text/mtgo/moxfield/archidekt
  -o decks/my_deck.txt \         # Output path (default: decks/<commander>.txt)
  -v                             # Verbose — show why each card was picked
```

## Deck Variety

By default, builds are deterministic — the same collection + commander always produces the same deck. Use `--variety` / `--seed` / `--theme` when you want different, fresh decks instead of the same staples every time.

```bash
# Different deck each run (random seed printed so you can reproduce it)
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice" --variety 0.6

# Reproduce a specific build
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice" --variety 0.6 --seed 12345

# Steer the deck toward an archetype
commanderai build -c data/my_collection.txt -C "Y'shtola, Night's Blessed" --theme aristocrats
```

- `--variety 0.0` (default): deterministic top-picks, unchanged behavior.
- `--variety` up to `1.0`: score-weighted random sampling across card picks and the mana base, so re-runs differ while staying powerful. Also emphasizes commander synergy over raw EDHREC rank.
- `--seed N`: reproducible variety. Passing `--seed` alone turns on a moderate variety level.
- `--theme`: `aristocrats`, `tokens`, `spellslinger`, `lifegain`, `counters`, `graveyard`, `reanimator`, `blink`, `voltron`, `landfall`, `control`. Theme steering is deterministic on its own and composes with `--variety`.
- In AI mode, variety also shuffles the candidate ordering and feeds prior saved decks to Claude with a "build something different" instruction.

`--variety` / `--seed` also work on `suggest-commanders` and `suggest` (surface different picks each run), and `suggest` accepts `--theme` too:

```bash
# Different commander ideas each run
commanderai suggest-commanders -c data/my_collection.txt --variety 0.7

# Themed, varied upgrade suggestions
commanderai suggest -c data/my_collection.txt -C "Y'shtola, Night's Blessed" --theme aristocrats --variety 0.6
```

## Build by Theme (no commander needed)

You don't have to know which commander to build. Give a `--theme` and/or `--colors` and CommanderAI picks the best-fit legal commander you own, then builds the deck.

```bash
# Auto-pick the best aristocrats commander you own
commanderai build -c data/my_collection.txt --theme aristocrats

# Constrain to a color combination (name or WUBRG letters)
commanderai build -c data/my_collection.txt --colors jund --theme dragons
commanderai build -c data/my_collection.txt --colors WUB --theme spellslinger

# Just colors, no theme — best goodstuff commander in those colors
commanderai build -c data/my_collection.txt --colors azorius
```

### Themes / archetypes

> Tip: run `commanderai list themes`, `list tribes`, `list aliases`, or `list colors` to see every accepted value.

`--theme` accepts:

- **Archetypes**: `aristocrats`, `tokens`, `spellslinger`, `lifegain`, `lifedrain`, `counters`, `graveyard`, `reanimator`, `mill`, `blink`, `voltron`, `equipment`, `auras`, `enchantress`, `landfall`, `ramp`, `artifacts`, `treasure`, `food`, `clues`, `wheels`, `group_hug`, `burn`, `stax`, `taxes`, `superfriends`, `vehicles`, `sagas`, `toolbox`, `pillow_fort`, `fog`, `theft`, `clone`, `cascade`, `infect`, `discard`, `land_destruction`, `extra_combat`, `control`
- **Tribes**: `elf`, `goblin`, `zombie`, `vampire`, `dragon`, `angel`, `sliver`, `merfolk`, `human`, `wizard`, ... (and more)
- **Aliases**: `go-wide`→tokens, `storm`→spellslinger, `bogles`→auras, `tron`→ramp, `death-and-taxes`→taxes, `8-rack`→discard, `ponza`→land-destruction, `self-mill`→mill, ...

### Color names

`--colors` accepts WUBRG letters (`WUB`) or a combination name: guilds (`azorius`, `dimir`, `rakdos`, `gruul`, `selesnya`, `orzhov`, `izzet`, `golgari`, `boros`, `simic`), shards/wedges (`esper`, `grixis`, `jund`, `naya`, `bant`, `jeskai`, `sultai`, `mardu`, `temur`, `abzan`), four-color (`yore-tiller`, `glint-eye`, `dune-brood`, `ink-treader`, `witch-maw`), and `five-color`.

## Partners (two commanders)

Some commanders can share the command zone. Pass a second commander with `--partner` / `-P`:

```bash
commanderai build -c data/my_collection.txt \
  -C "Thrasios, Triton Hero" -P "Tymna the Weaver"
```

Supported pairings: plain **Partner**, **Partner with X**, restricted **Partner — group**, **Friends forever**, **Choose a Background** + a **Background** enchantment, and **Doctor's companion** + a **Time Lord Doctor**. Illegal pairs are rejected.

The deck uses the **combined color identity**, both commanders feed synergy scoring and the mana base, and the deck is built as 2 commanders + 98 cards = 100. When auto-picking (no `--commander`), if the chosen commander wants a partner, the best-fit one you own is auto-selected too.

## Power Brackets

Control deck power level with `--bracket` (`-b`). Uses [Commander Spellbook](https://commanderspellbook.com/) API to detect combos and problematic cards in real time.

| Bracket | Style | What's allowed |
|---------|-------|----------------|
| 1 | Exhibition | No game changers, no combos, no extra turns, no MLD |
| 2 | Core | No game changers, no two-card combos, no extra turns, no MLD |
| 3 | Upgraded | Up to 3 game changers, 1 late-game combo (≥6 mana), no extra turn chains, no MLD |
| 4 | Optimized | No restrictions (only banlist) |
| 5 | cEDH | Same as 4, no filtering applied |

```bash
# Casual game night — no Rhystic Study, no Cyclonic Rift, no infinite combos
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice" -b 2

# Focused but fair — strong synergy allowed, no instant-win combos
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice" -b 3

# Full power
commanderai build -c data/my_collection.txt -C "Atraxa, Praetors' Voice" -b 5
```

The bracket filter shows exactly which cards and combos were excluded, so you can see what got cut and why.

**Offline:** when Commander Spellbook can't be reached — or with `COMMANDERAI_OFFLINE=1`, which disables every network call — the same bracket limits are applied from local card data: game changers (Scryfall's `game_changer` flag), extra-turn and mass-land-denial cards (rules text). Combos can't be detected offline; the build says so.

## Output

Every build is stored in the deck database (`data/commanderai.db`, override with `COMMANDERAI_DB`) — the single source of truth — and exported to the `decks/` directory. Running build with the same commander creates numbered files (`atraxa.txt`, `atraxa_2.txt`, `atraxa_3.txt`...) — previous builds are never overwritten.

```bash
commanderai decks list                       # saved decks, newest first
commanderai decks show 3 -v                  # deck + build parameters (theme, seed, budget…)
commanderai decks export 3 -f moxfield       # or json / text / mtgo / archidekt, -o FILE
commanderai decks import deck.json           # JSON export or any text decklist
commanderai decks rename 3 "Spicy Atarka"
commanderai decks delete 3
commanderai decks migrate                    # import legacy decks/*.txt files
```

Existing `decks/*.txt` files from earlier versions are imported into the database automatically the first time the deck library is used.

## Testing

```bash
scripts/test.sh          # unit tests, lint, golden CLI snapshots, differential test
scripts/test.sh quick    # ~10 seconds
```

See [docs/TESTING.md](docs/TESTING.md) for what each suite proves and the expected results.

## How It Works

1. **Parse** your collection (supports "1 CardName" text or CSV from Archidekt/Moxfield)
2. **Filter** to commander's color identity + Commander-legal cards
3. **Classify** each card into roles: ramp, draw, removal, wipes, threats, utility
4. **Score** using EDHREC rank + keyword synergy with commander + mana curve
5. **Pick** final 99 via heuristics or Claude AI (hybrid mode)
6. **Build mana base** proportional to color pip distribution, prioritizing duals/fetches you own

## Collection Format

Supports multiple formats:

```
# Simple text (one per line)
1 Sol Ring
1 Command Tower
2 Forest

# With set code
1 Sol Ring (C21)

# CSV (Archidekt export)
Quantity,Name,Edition Code,...
1,Sol Ring,c21,...
```

## Token Tracking

```bash
# See all tokens your deck needs
commanderai tokens -d decks/atraxa.txt
```

Shows each unique token with P/T, colors, keywords, and which cards create it — so you know which token cards to bring to the table.

## Upgrade Suggestions

```bash
# Heuristic (free, instant)
commanderai suggest -c data/my_collection.txt -C "Avatar Aang // Aang, Master of Elements" --no-llm --top 20

# AI-powered (needs API key, explains WHY each card is good)
commanderai suggest -c data/my_collection.txt -C "Avatar Aang // Aang, Master of Elements"
```

## Edge Cases

- **Small collections** (<100 cards): warns you upfront, builds best possible deck with available cards, fills remaining slots with basic lands
- **Not enough on-color cards**: detects thin pools, adjusts land count upward, notifies you
- **Tokens/special cards in collection**: automatically detected and skipped (not reported as errors)
- **LLM returns too few picks**: backfills from heuristic candidates, then pads with basics to guarantee 100 cards

## Requirements

- Python 3.11+
- [Anthropic API key](https://console.anthropic.com) (optional — only for AI features)

## Project Structure

```
CommanderAI/
├── src/commanderai/
│   ├── cli/                # Typer commands + console rendering (thin front-end)
│   ├── services/           # All use-cases (build, commanders, collection, analysis, ...)
│   ├── settings.py         # Runtime settings from the environment
│   ├── errors.py           # Typed, user-facing errors
│   ├── reporting.py        # Structured progress/notice reporting
│   ├── catalog.py          # Cached card-catalog loading
│   ├── config.py           # Static configuration and constants
│   ├── models.py           # Card, Deck, DeckSlot models
│   ├── collection/         # Parse + match collection files
│   ├── data/               # Scryfall bulk data + card index
│   ├── deckbuilder/        # Scoring, slots, candidates, LLM, mana base
│   └── output/             # Formatting and export
├── src/commanderai/storage/  # SQLite deck database (decks, collections)
├── src/commanderai/api/    # HTTP API (FastAPI) serving the web UI
├── web/                    # Web UI (React + Mantine + Vite), built into web/dist
├── scripts/                # setup.sh, test.sh, golden.py, difftest.py, check_example.py, demo
├── docs/ARCHITECTURE.md    # Layers, service API, deck database, notice/error codes
├── docs/TESTING.md         # How to run the tests and what to expect
├── docs/UI_PLAN.md         # Web UI: stack, API contract, screens, delivery plan
├── decks/                  # Generated decks (gitignored)
├── data/                   # Local collection + cached card DB
└── tests/
```

## License

MIT
