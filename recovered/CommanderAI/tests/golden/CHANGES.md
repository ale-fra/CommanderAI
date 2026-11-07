# Documented behaviour changes since 0.7.0

`scripts/golden.py compare --documented` compares the current CLI with the
original 0.7.0 snapshot in `baseline/` and accepts exactly the differences
listed here (the rules live in `DOCUMENTED_CHANGES` in `scripts/golden.py`).
Everything else must still be byte-for-byte identical.

## Phase B — service-layer refactor

No visible change in any golden case. Only paths that used to crash now print
a message instead of a Python traceback (not part of the golden matrix):
missing `-d/--deck` or `-i/--input` file, missing card database, and invalid
option values such as `--lands 150` (allowed range 0–99).

## Phase C — SQLite deck database

| Id | Change | Effect on the golden cases |
|---|---|---|
| C1 | `build` stores every deck in the database (single source of truth) and still writes the text export. The confirmation line gains the database id: `Deck saved → decks/zaxara__the_exemplary.txt (deck #1)` | Every `build` case: that one line. Rewrite rule strips ` (deck #N)`. |
| C2 | `list decks` reads the database instead of scanning `decks/*.txt`. New layout: `#id  name [colors] — N cards, $price` plus a `source · created · file` line; new empty message `No saved decks yet. Build a deck first.` (the card count is now correct: 100, not 99 — fix D4 comes for free). | `list-decks-empty`, `list-decks-after-builds` superseded. |
| C3 | Each case records a dump of the deck database (`db-dump.txt`). | Not present in the baseline; ignored there. |
| C4 | On the first use of the deck library, existing legacy `decks/*.txt` files are imported into the database once, printing `Imported N legacy deck file(s) from <dir> into the deck database` (and one warning per file that is not a deck). | Only in new cases (`legacy-migration`, `decks-*`). |
| C5 | `build -f <unknown>` fails immediately with `Unknown format '<x>'. Options: text, mtgo, moxfield, archidekt` (exit 1) instead of crashing with a traceback after building. | New case `build-err-bad-format`. |
| C6 | New `decks` command group: `list`, `show`, `export`, `import`, `rename`, `delete`, `migrate`. | New cases `decks-*`, `legacy-*`. |
| C7 | LLM "build something different" (`--variety`/`--seed` without `--no-llm`) takes the previous decks for that commander from the database instead of globbing text files; land cards are no longer sent in that list. | New case `build-llm-prior-decks`. |

## Phase D — bug fixes

The golden harness runs with `COMMANDERAI_OFFLINE=1` so results never depend on
network access.

| Id | Fix | Effect on the golden cases |
|---|---|---|
| D1 | `validate` counts quantities (`15 Plains` = 15 cards); the commander/partner may be listed or not and are counted once; new checks: the commander can be a commander, the two commanders can partner; new `--partner/-P`; unknown cards are reported (`N card(s) not recognised (not counted): …`). All five precons and the supplied Zaxara list now validate: `Deck is valid! (100 cards)` instead of `Deck has 71 cards…`. | `validate-precon-first-flight`, `validate-precon-grave-danger`, `validate-zaxara-decklist` changed; new `validate-precon-*`, `validate-errors`. |
| D2 | One price rule everywhere (`Card.price_usd`: nonfoil → foil → etched; unknown = $0) used by the deck summary, the budget, the CLI and the LLM prompt. The budget covers all 100 cards **including the commander(s)**: candidates above the budget left after the commanders are dropped, swaps continue until the whole deck fits, and `Budget: deck fits at $X` now equals `Est. price: $X`. New warning when the commander(s) alone exceed the budget. | Prices are masked on both sides (`Est. price`, `deck fits at`, `best is`, suggestion prices), so every other line is still verified. `--budget` builds whose picks changed (7 cases, e.g. `build-atarka-budget1`: $0.61 left after Atarka → 59 instead of 49 cards dropped; Syr Konrad: one extra swap) are reported as changed. New `build-gargos-commander-over-budget`, `build-muldrotha-bracket2-budget`. |
| D3 | Power brackets work offline. When Commander Spellbook is unreachable (or `COMMANDERAI_OFFLINE=1`), game changers (Scryfall `game_changer` flag), extra-turn and mass-land-denial cards (oracle text) are filtered with the same per-bracket rules (bracket 3 keeps the 3 most popular game changers and prioritises them). A warning says so and that combos were not checked: `Bracket 2: offline mode — applied offline rules (game changers, extra turns, mass land denial); combos not checked.` Online, the partner is now sent to Spellbook too. | `build-zaxara-bracket2`: Rhystic Study and Mystical Tutor excluded (replaced by Ponder and Curse of the Swine). New `build-zaxara-bracket1`, `build-zaxara-bracket3`. |
| D4 | `list decks` showed 99 cards for decks saved in the grouped text format. | Fixed by C2 (the list now comes from the database). |
| D5 | `tokens`: predefined artifact tokens get their type (`• Artifact — Food` instead of `• — Food`); `tapped`/`untapped` are no longer part of a token name (`tapped Zombie` merges into `Zombie`); copy tokens (`create a token that's a copy of …`, incl. Eternalize/Embalm reminder text) are listed as `• Copy of a permanent` instead of garbled names. | 4 `tokens-*` cases changed; new `tokens-precon-grave-danger`, `tokens-precon-chaos-incarnate`. |
| D6 | `COMMANDERAI_OFFLINE=1` disables every network call: brackets use the offline rules, the LLM is not called even with an API key (`LLM failed (offline mode …), falling back to heuristic`), `update-data` refuses to download. | New `update-data-offline`. |

Also new in the data model (no CLI output change): `Card.game_changer`,
`Card.price_usd`, `Deck.unpriced_cards` (cards with no price data — 49 of the
500 catalog cards, e.g. Sol Ring, count as $0), `BudgetReport.commanders_price`,
`BracketReport.mode` / `offline_reason`.

## Web UI M1 — no CLI behaviour change

`Card` gained `rarity` and `set_name`, and the build request gained
`collection_label` (null for CLI builds). They only appear in JSON deck exports,
so `tests/golden/expected/` was re-captured for `decks-lifecycle` and
`decks-export-formats` (added lines only). The baseline comparison is unaffected.
