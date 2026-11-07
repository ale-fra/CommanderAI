# Golden-master snapshots

| Directory | Content | Regenerate? |
|---|---|---|
| `baseline/` | CLI behaviour of the **original CommanderAI 0.7.0**, captured from the untouched pre-refactor code | **Never** (the harness refuses) |
| `expected/` | The current intended behaviour (all cases, including the deck-database ones) | Only for intentional, documented changes |
| `reference/cli_0_7_0.py` | The original `cli.py`, used by `scripts/difftest.py` | Never |
| `CHANGES.md` | Every intentional difference between `baseline/` and the current code | Whenever behaviour changes on purpose |

Each case directory holds, per CLI invocation, `stepN.out` (the command, its exit
code and console output), every file the command wrote (`decks/*.txt`, `-o`
outputs) and, when a deck database exists, `db-dump.txt`.

```sh
python scripts/golden.py list                    # case names
python scripts/golden.py compare                 # current code vs expected/
python scripts/golden.py compare --documented    # current code vs baseline/ + CHANGES.md
python scripts/golden.py compare -k decks-       # subset
python scripts/golden.py changes                 # documented changes
```

See `docs/TESTING.md` for the full testing guide.
