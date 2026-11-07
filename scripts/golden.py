#!/usr/bin/env python3
"""Golden-master harness for the CommanderAI CLI.

Runs a fixed matrix of CLI invocations against the bundled offline data and
records, for every case, the exit code, the (normalised) console output and
every file the command wrote. Used to prove that refactors keep behaviour
identical, and to document intended behaviour changes.

Usage:
    python scripts/golden.py compare                  # current code vs tests/golden/expected
    python scripts/golden.py compare --documented     # vs the original 0.7.0 baseline, allowing
                                                      #   only the changes documented below
    python scripts/golden.py capture --dest DIR       # (re)write a snapshot
    python scripts/golden.py list                     # case names
    python scripts/golden.py changes                  # the documented behaviour changes

Each case runs in a fresh subprocess (``python -m commanderai.cli``) with:
- the offline catalog (COMMANDERAI_CACHE=offline-data),
- a per-run scratch working directory containing an empty ``decks/`` folder
  (COMMANDERAI_DECKS_DIR=decks, so printed paths are stable and relative),
- no API key, fixed terminal width, fixed hash seed.

Normalisation is deliberately minimal: Rich spinner lines (whose frame glyph
depends on timing) are dropped, the repository / scratch paths become ``<ROOT>`` /
``<WORK>`` and timestamps become ``<TIME>``. Everything else must match
byte-for-byte. When the deck database exists after a case, a deterministic dump
of it is recorded as ``db-dump.txt``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OFFLINE = ROOT / "offline-data"
SAMPLE = ROOT / "commanderai-sample"
PRECONS = SAMPLE / "precons"
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN_DIR = ROOT / "tests" / "golden"
BASELINE = GOLDEN_DIR / "baseline"      # original 0.7.0 behaviour — never regenerated
EXPECTED = GOLDEN_DIR / "expected"      # current intended behaviour
DEFAULT_SNAPSHOT = EXPECTED
DB_DUMP = "db-dump.txt"

EXPANDED = SAMPLE / "expanded-collection.txt"

_SPINNER_CHARS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


@dataclass
class Case:
    name: str
    steps: list[list[str]]  # one or more CLI invocations run in the same workdir
    collection: Path | None = EXPANDED  # COMMANDERAI_COLLECTION (None = unset)
    files: list[str] = field(default_factory=list)  # extra files (relative) to snapshot
    # Files created in the scratch dir before the first step: (dest, source) where
    # source is "baseline:<case>/<path>" (a file from the baseline snapshot) or
    # literal text. Seeded files get fixed, increasing modification times.
    seed: list[tuple[str, str]] = field(default_factory=list)


def _build(*args: str) -> list[str]:
    return ["build", *args]


def cases() -> list[Case]:
    c: list[Case] = []

    # ---- list / reference vocabularies -------------------------------------
    for cat in ["colors", "themes", "tribes", "aliases", "formats", "brackets"]:
        c.append(Case(f"list-{cat}", [["list", cat]]))
    c.append(Case("list-commanders", [["list", "commanders"]]))
    c.append(Case("list-commanders-jund-head", [["list", "commanders", "--colors", "jund", "--head", "3"]]))
    c.append(Case("list-commanders-tail", [["list", "commanders", "--tail", "4"]]))
    c.append(Case("list-commanders-precon", [["list", "commanders", "-c", str(PRECONS / "grave-danger.txt")]]))
    c.append(Case("list-head-and-tail-error", [["list", "commanders", "--head", "2", "--tail", "2"]]))
    c.append(Case("list-decks-empty", [["list", "decks"]]))
    c.append(Case(
        "list-decks-after-builds",
        [
            _build("-C", "Zaxara, the Exemplary", "--no-llm"),
            _build("-C", "Atarka, World Render", "--no-llm", "-f", "archidekt"),
            _build("-C", "Zaxara, the Exemplary", "--no-llm", "-f", "moxfield"),
            ["list", "decks"],
            ["list", "decks", "--head", "1"],
        ],
    ))

    # ---- suggest-commanders --------------------------------------------------
    c.append(Case("suggest-commanders-default", [["suggest-commanders"]]))
    c.append(Case("suggest-commanders-top10", [["suggest-commanders", "--top", "10"]]))
    c.append(Case("suggest-commanders-theme", [["suggest-commanders", "--theme", "tokens", "--top", "3"]]))
    c.append(Case("suggest-commanders-colors", [["suggest-commanders", "--colors", "simic", "--top", "10"]]))
    c.append(Case("suggest-commanders-variety", [["suggest-commanders", "--variety", "0.7", "--seed", "3"]]))
    c.append(Case("suggest-commanders-seed-only", [["suggest-commanders", "--seed", "11", "--top", "4"]]))
    c.append(Case("suggest-commanders-bad-theme", [["suggest-commanders", "--theme", "nonsense"]]))

    # ---- build: explicit commander ------------------------------------------
    c.append(Case("build-zaxara", [_build("-C", "Zaxara, the Exemplary", "--no-llm")]))
    c.append(Case("build-zaxara-verbose", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-v")]))
    c.append(Case("build-zaxara-lands33", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "--lands", "33")]))
    c.append(Case("build-zaxara-theme", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "--theme", "counters")]))
    c.append(Case("build-zaxara-bracket2", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-b", "2")]))
    c.append(Case("build-zaxara-bracket5", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-b", "5")]))
    c.append(Case("build-zaxara-llm-fallback", [_build("-C", "Zaxara, the Exemplary")]))
    c.append(Case("build-zaxara-llm-fallback-variety", [_build("-C", "Zaxara, the Exemplary", "--seed", "5")]))
    c.append(Case("build-atarka-budget40", [_build("-C", "Atarka, World Render", "--no-llm", "--budget", "40")]))
    c.append(Case("build-atarka-budget1", [_build("-C", "Atarka, World Render", "--no-llm", "--budget", "1")]))
    c.append(Case("build-kardur-variety", [_build("-C", "Kardur, Doomscourge", "--no-llm", "--variety", "0.8", "--seed", "42")]))
    c.append(Case("build-muldrotha-seed-only", [_build("-C", "Muldrotha, the Gravetide", "--no-llm", "--seed", "99")]))
    c.append(Case("build-format-archidekt", [_build("-C", "Emmara, Soul of the Accord", "--no-llm", "-f", "archidekt")]))
    c.append(Case("build-format-moxfield", [_build("-C", "Emmara, Soul of the Accord", "--no-llm", "-f", "moxfield")]))
    c.append(Case("build-format-mtgo", [_build("-C", "Emmara, Soul of the Accord", "--no-llm", "-f", "mtgo")]))
    c.append(Case("build-output-path", [_build("-C", "Isperia, Supreme Judge", "--no-llm", "-o", "custom.txt")], files=["custom.txt"]))
    c.append(Case("build-repeat-numbering", [
        _build("-C", "Syr Konrad, the Grim", "--no-llm"),
        _build("-C", "Syr Konrad, the Grim", "--no-llm"),
        _build("-C", "Syr Konrad, the Grim", "--no-llm", "--variety", "0.5", "--seed", "1"),
    ]))

    # ---- build: auto-pick ----------------------------------------------------
    c.append(Case("build-auto-theme-tokens", [_build("--theme", "tokens", "--no-llm")]))
    c.append(Case("build-auto-theme-dragons-variety", [_build("--theme", "dragons", "--no-llm", "--variety", "0.5", "--seed", "7")]))
    c.append(Case("build-auto-colors-azorius", [_build("--colors", "azorius", "--no-llm")]))
    c.append(Case("build-auto-colors-theme", [_build("--colors", "BG", "--theme", "graveyard", "--no-llm")]))
    c.append(Case("build-auto-alias", [_build("--theme", "go-wide", "--no-llm", "--budget", "75")]))
    c.append(Case("build-auto-colors-mardu-dragons", [_build("--colors", "mardu", "--theme", "dragons", "--no-llm")]))
    c.append(Case("build-auto-no-match", [_build("--colors", "colorless", "--theme", "dragons", "--no-llm")]))

    # ---- build: small / precon collections ----------------------------------
    c.append(Case("build-precon-first-flight", [_build("-C", "Isperia, Supreme Judge", "--no-llm", "-c", str(PRECONS / "first-flight.txt"))]))
    c.append(Case("build-precon-grave-danger-theme", [_build("-C", "Gisa and Geralf", "--no-llm", "--theme", "zombies", "-c", str(PRECONS / "grave-danger.txt"))]))
    c.append(Case("build-sample-collection", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-c", str(SAMPLE / "sample-collection.txt"))]))
    c.append(Case("build-csv-collection", [_build("-C", "Tatyova, Benthic Druid", "--no-llm", "-c", str(SAMPLE / "expanded-collection.csv"))]))
    c.append(Case("build-tiny-collection", [_build("-C", "Atraxa, Praetors' Voice", "--no-llm", "-c", str(FIXTURES / "tiny_collection.txt"))]))

    # ---- build: errors -------------------------------------------------------
    c.append(Case("build-err-no-args", [_build("--no-llm")]))
    c.append(Case("build-err-bad-theme", [_build("--theme", "nonsense", "--no-llm")]))
    c.append(Case("build-err-bad-colors", [_build("--colors", "purple", "--no-llm")]))
    c.append(Case("build-err-unknown-commander", [_build("-C", "Not A Real Card", "--no-llm")]))
    c.append(Case("build-err-illegal-commander", [_build("-C", "Sol Ring", "--no-llm")]))
    c.append(Case("build-err-partner-without-commander", [_build("-P", "Muldrotha, the Gravetide", "--theme", "tokens", "--no-llm")]))
    c.append(Case("build-err-illegal-partner", [_build("-C", "Zaxara, the Exemplary", "-P", "Muldrotha, the Gravetide", "--no-llm")]))
    c.append(Case("build-err-unknown-partner", [_build("-C", "Zaxara, the Exemplary", "-P", "Nobody Here", "--no-llm")]))
    c.append(Case("build-err-missing-collection", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-c", "missing.txt")]))
    c.append(Case("build-err-default-collection-missing", [_build("-C", "Zaxara, the Exemplary", "--no-llm")], collection=Path("nope/none.txt")))

    # ---- tokens / validate / explain / suggest / convert -------------------
    c.append(Case("tokens-built-deck", [
        _build("-C", "Zaxara, the Exemplary", "--no-llm"),
        ["tokens", "-d", "decks/zaxara__the_exemplary.txt"],
    ]))
    c.append(Case("tokens-archidekt-deck", [
        _build("-C", "Emmara, Soul of the Accord", "--no-llm", "-f", "archidekt"),
        ["tokens", "-d", "decks/emmara__soul_of_the_accord.txt"],
    ]))
    for precon in ["token-triumph", "draconic-destruction", "first-flight"]:
        c.append(Case(f"tokens-precon-{precon}", [["tokens", "-d", str(PRECONS / f"{precon}.txt")]]))
    c.append(Case("validate-precon-first-flight", [["validate", "-d", str(PRECONS / "first-flight.txt"), "-C", "Isperia, Supreme Judge"]]))
    c.append(Case("validate-precon-grave-danger", [["validate", "-d", str(PRECONS / "grave-danger.txt"), "-C", "Gisa and Geralf"]]))
    c.append(Case("validate-zaxara-decklist", [["validate", "-d", str(SAMPLE / "supplied-zaxara-decklist.txt"), "-C", "Zaxara, the Exemplary"]]))
    c.append(Case("validate-built-deck", [
        _build("-C", "Kardur, Doomscourge", "--no-llm", "-f", "mtgo"),
        ["validate", "-d", "decks/kardur__doomscourge.txt", "-C", "Kardur, Doomscourge"],
    ]))
    c.append(Case("validate-unknown-commander", [["validate", "-d", str(PRECONS / "first-flight.txt"), "-C", "Nobody"]]))
    c.append(Case("explain-no-key", [["explain", "-d", str(PRECONS / "first-flight.txt")]]))
    c.append(Case("explain-no-commander", [["explain", "-d", str(FIXTURES / "tiny_collection.txt"), "-C", "Nobody"]]))
    c.append(Case("suggest-full-collection", [["suggest", "-C", "Zaxara, the Exemplary", "--no-llm"]]))
    c.append(Case("suggest-precon", [["suggest", "-C", "Isperia, Supreme Judge", "--no-llm", "--top", "5", "-c", str(PRECONS / "first-flight.txt")]]))
    c.append(Case("suggest-precon-theme-variety", [["suggest", "-C", "Kardur, Doomscourge", "--no-llm", "--top", "6", "--theme", "burn", "--seed", "4", "-c", str(PRECONS / "chaos-incarnate.txt")]]))
    c.append(Case("suggest-llm-no-key", [["suggest", "-C", "Isperia, Supreme Judge", "-c", str(PRECONS / "first-flight.txt")]]))
    c.append(Case("suggest-unknown-commander", [["suggest", "-C", "Nobody", "--no-llm"]]))
    c.append(Case("convert-csv-stdout", [["convert", "-i", str(SAMPLE / "sample-collection.csv")]]))
    c.append(Case("convert-csv-file", [["convert", "-i", str(SAMPLE / "expanded-collection.csv"), "-o", "converted.txt"]], files=["converted.txt"]))
    c.append(Case("convert-empty", [["convert", "-i", "empty.txt"]]))

    # ---- deck database (phase C) ------------------------------------------------
    zax = _build("-C", "Zaxara, the Exemplary", "--no-llm")
    c.append(Case("decks-list-empty", [["decks", "list"]]))
    c.append(Case("decks-lifecycle", [
        zax,
        _build("-C", "Emmara, Soul of the Accord", "--no-llm", "-f", "archidekt", "--theme", "tokens"),
        ["decks", "list"],
        ["decks", "show", "1"],
        ["decks", "show", "2", "-v"],
        ["decks", "export", "1", "-f", "json", "-o", "zaxara.json"],
        ["decks", "import", "zaxara.json", "--name", "Zaxara copy"],
        ["decks", "rename", "3", "Zaxara (imported)"],
        ["decks", "delete", "1"],
        ["decks", "list", "--commander", "Zaxara, the Exemplary"],
        ["list", "decks", "--tail", "1"],
        ["decks", "show", "1"],
    ], files=["zaxara.json"]))
    c.append(Case("decks-export-formats", [
        _build("-C", "Kardur, Doomscourge", "--no-llm", "--budget", "60"),
        ["decks", "export", "1", "-f", "text"],
        ["decks", "export", "1", "-f", "text", "-v"],
        ["decks", "export", "1", "-f", "mtgo"],
        ["decks", "export", "1", "-f", "moxfield"],
        ["decks", "export", "1", "-f", "archidekt"],
        ["decks", "export", "1"],
    ]))
    c.append(Case("decks-import-text", [
        ["decks", "import", "atarka.txt"],
        ["decks", "import", "partial.txt"],
        ["decks", "import", "garbage.txt"],
        ["decks", "import", "missing.json"],
        ["decks", "show", "2"],
        ["decks", "list"],
    ], seed=[
        ("atarka.txt", "baseline:all-atarka--world-render/decks/atarka__world_render.txt"),
        ("partial.txt", "1 Isperia, Supreme Judge\n1 Sol Ring\n1 Not A Real Card\n2 Island\n"),
        ("garbage.txt", "hello\nworld\n"),
    ]))
    c.append(Case("decks-errors", [
        zax,
        ["decks", "show", "99"],
        ["decks", "export", "99"],
        ["decks", "export", "1", "-f", "pdf"],
        ["decks", "rename", "99", "x"],
        ["decks", "rename", "1", "   "],
        ["decks", "delete", "99"],
        ["decks", "list", "--head", "1", "--tail", "1"],
    ]))
    c.append(Case("legacy-migration", [
        ["list", "decks"],
        ["decks", "show", "3"],
        ["decks", "show", "1", "-v"],
        ["decks", "migrate"],
        zax,
        ["decks", "list", "--head", "2"],
    ], seed=[
        ("decks/zaxara__the_exemplary.txt", "baseline:build-zaxara/decks/zaxara__the_exemplary.txt"),
        ("decks/zaxara__the_exemplary_2.txt", "baseline:build-zaxara-verbose/decks/zaxara__the_exemplary.txt"),
        ("decks/emmara_archidekt.txt", "baseline:build-format-archidekt/decks/emmara__soul_of_the_accord.txt"),
        ("decks/emmara_moxfield.txt", "baseline:build-format-moxfield/decks/emmara__soul_of_the_accord.txt"),
        ("decks/emmara_mtgo.txt", "baseline:build-format-mtgo/decks/emmara__soul_of_the_accord.txt"),
        ("decks/kardur_variety.txt", "baseline:build-kardur-variety/decks/kardur__doomscourge.txt"),
        ("decks/notes.txt", "just some notes\nnot a deck\n"),
    ]))
    c.append(Case("legacy-no-resurrect", [
        zax,
        ["decks", "delete", "1"],
        ["decks", "migrate"],
        ["list", "decks"],
    ]))
    c.append(Case("build-llm-prior-decks", [
        _build("-C", "Zaxara, the Exemplary", "--seed", "5"),
        _build("-C", "Zaxara, the Exemplary", "--seed", "6"),
        _build("-C", "Zaxara, the Exemplary", "--seed", "7", "-f", "mtgo"),
    ]))
    c.append(Case("build-err-bad-format", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-f", "bogus")]))

    # ---- bug fixes (phase D) ------------------------------------------------------
    for precon, cmdr in [("chaos-incarnate", "Kardur, Doomscourge"),
                         ("draconic-destruction", "Atarka, World Render"),
                         ("token-triumph", "Emmara, Soul of the Accord")]:
        c.append(Case(f"validate-precon-{precon}",
                      [["validate", "-d", str(PRECONS / f"{precon}.txt"), "-C", cmdr]]))
    c.append(Case("validate-errors", [
        ["validate", "-d", str(PRECONS / "first-flight.txt"), "-C", "Sol Ring"],
        ["validate", "-d", str(PRECONS / "first-flight.txt"), "-C", "Isperia, Supreme Judge",
         "-P", "Gisa and Geralf"],
        ["validate", "-d", "short.txt", "-C", "Isperia, Supreme Judge"],
        ["validate", "-d", "quantities.txt", "-C", "Isperia, Supreme Judge"],
        ["validate", "-d", "duplicates.txt", "-C", "Isperia, Supreme Judge"],
    ], seed=[
        ("short.txt", "1 Isperia, Supreme Judge\n1 Sol Ring\n1 Not A Real Card\n"),
        ("quantities.txt", "1 Isperia, Supreme Judge\n1 Sol Ring\n98 Island\n"),
        ("duplicates.txt", "2 Sol Ring\n97 Island\n"),
    ]))
    c.append(Case("build-zaxara-bracket1", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-b", "1")]))
    c.append(Case("build-zaxara-bracket3", [_build("-C", "Zaxara, the Exemplary", "--no-llm", "-b", "3", "-v")]))
    c.append(Case("build-muldrotha-bracket2-budget", [
        _build("-C", "Muldrotha, the Gravetide", "--no-llm", "-b", "2", "--budget", "70")]))
    c.append(Case("build-gargos-commander-over-budget", [
        _build("-C", "Gargos, Vicious Watcher", "--no-llm", "--budget", "1")]))
    for precon in ["grave-danger", "chaos-incarnate"]:
        c.append(Case(f"tokens-precon-{precon}", [["tokens", "-d", str(PRECONS / f"{precon}.txt")]]))
    c.append(Case("update-data-offline", [["update-data"]]))

    # ---- every owned commander, default heuristic build ---------------------
    for name in _ALL_COMMANDERS:
        slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
        c.append(Case(f"all-{slug}", [_build("-C", name, "--no-llm")]))
        c.append(Case(f"all-{slug}-budget-theme", [_build("-C", name, "--no-llm", "--budget", "50", "--theme", "tokens", "--seed", "3")]))
    return c


_ALL_COMMANDERS = [
    "Syr Konrad, the Grim", "Selvala, Heart of the Wilds", "Tatyova, Benthic Druid",
    "Rishkar, Peema Renegade", "Kardur, Doomscourge", "Muldrotha, the Gravetide",
    "Drakuseth, Maw of Flames", "Tekuthal, Inquiry Dominus", "Sephara, Sky's Blade",
    "Atarka, World Render", "Kazuul, Tyrant of the Cliffs", "Inga and Esika",
    "Kaervek the Merciless", "Ezuri, Stalker of Spheres", "Maja, Bretagard Protector",
    "Gisa and Geralf", "Gargos, Vicious Watcher", "Zegana, Utopian Speaker",
    "Kangee, Sky Warden", "Zaxara, the Exemplary", "Emmara, Soul of the Accord",
    "Josu Vess, Lich Knight", "The Mimeoplasm", "Isperia, Supreme Judge",
    "Verix Bladewing", "Trostani Discordant", "Vela the Night-Clad",
]


def _env(case: Case) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(SRC),
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "COLUMNS": "120",
        "LINES": "50",
        "TERM": "dumb",
        "NO_COLOR": "1",
        "COMMANDERAI_CACHE": str(OFFLINE),
        "COMMANDERAI_DECKS_DIR": "decks",
        # Keep any local deck database inside the scratch dir (used after the
        # storage layer lands; harmless before).
        "COMMANDERAI_DB": "scratch.db",
        "ANTHROPIC_API_KEY": "",
        # Never call external services: results must not depend on network access.
        "COMMANDERAI_OFFLINE": "1",
    }
    if case.collection is not None:
        env["COMMANDERAI_COLLECTION"] = str(case.collection)
    return env


_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[+-]\d{2}:\d{2}|Z)?")


def _normalise(text: str, work: Path | None = None) -> str:
    text = text.replace(str(ROOT), "<ROOT>")
    if work is not None:
        text = text.replace(str(work.resolve()), "<WORK>").replace(str(work), "<WORK>")
    text = _TIME_RE.sub("<TIME>", text)
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped[0] in _SPINNER_CHARS:
            continue
        out.append(line.rstrip())
    return "\n".join(out) + "\n"


def _normalise_file(text: str, work: Path) -> str:
    """Files: only paths and timestamps are normalised (content kept verbatim)."""
    text = text.replace(str(ROOT), "<ROOT>")
    text = text.replace(str(work.resolve()), "<WORK>").replace(str(work), "<WORK>")
    return _TIME_RE.sub("<TIME>", text)


def _seed(case: Case, work: Path) -> None:
    for i, (dest, source) in enumerate(case.seed):
        path = work / dest
        path.parent.mkdir(parents=True, exist_ok=True)
        if source.startswith("baseline:"):
            shutil.copyfile(BASELINE / source[len("baseline:"):], path)
        else:
            path.write_text(source, encoding="utf-8")
        stamp = 1_700_000_000 + i * 60
        os.utime(path, (stamp, stamp))


def dump_database(db_path: Path, work: Path) -> str:
    """Deterministic, timestamp-free text dump of the deck database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    lines = [f"schema version: {conn.execute('PRAGMA user_version').fetchone()[0]}", "", "== decks"]
    for row in conn.execute("SELECT * FROM decks ORDER BY id"):
        r = dict(row)
        record = json.loads(r.pop("record"))
        for k in ("created_at", "updated_at"):
            r.pop(k)
        lines.append(" | ".join(f"{k}={v}" for k, v in r.items()))
        deck = record["deck"]
        cmdrs = [deck["commander"]["name"]] + ([deck["partner"]["name"]] if deck.get("partner") else [])
        lines.append(f"    commanders: {' + '.join(cmdrs)}")
        by_slot: dict[str, list[str]] = {}
        for pick in deck["cards"]:
            by_slot.setdefault(pick["slot"], []).append(pick["card"]["name"])
        for slot in sorted(by_slot):
            lines.append(f"    {slot} ({len(by_slot[slot])}): {', '.join(sorted(by_slot[slot]))}")
        build = record.get("build") or {}
        if build:
            lines.append(
                f"    build: seed={build.get('seed')} variety={build.get('variety')} "
                f"theme={build.get('theme')} lands={build.get('lands')} "
                f"notices={[n['code'] for n in build.get('notices', [])]}"
            )
        if record.get("notes"):
            lines.append(f"    notes: {record['notes']}")
    lines += ["", "== collections"]
    for row in conn.execute("SELECT id, name, entries, copies FROM collections ORDER BY id"):
        lines.append(" | ".join(f"{k}={row[k]}" for k in row.keys()))  # noqa: SIM118 (sqlite3.Row iterates values)
    lines += ["", "== legacy_imports"]
    for row in conn.execute("SELECT path, status, deck_id, message FROM legacy_imports ORDER BY path"):
        lines.append(" | ".join(f"{k}={row[k]}" for k in row.keys()))  # noqa: SIM118 (sqlite3.Row iterates values)
    conn.close()
    return _normalise_file("\n".join(lines) + "\n", work)


def run_case(case: Case) -> dict[str, str]:
    """Run a case; return {relative_path: content} describing its results."""
    result: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="cai-golden-") as tmp:
        work = Path(tmp)
        (work / "empty.txt").write_text("")
        _seed(case, work)
        env = _env(case)
        for i, args in enumerate(case.steps, 1):
            proc = subprocess.run(
                [sys.executable, "-m", "commanderai.cli", *args],
                cwd=work, env=env, capture_output=True, text=True, timeout=300, check=False,
            )
            shown = " ".join(args).replace(str(ROOT), "<ROOT>")
            header = f"$ commanderai {shown}\n# exit code: {proc.returncode}\n"
            result[f"step{i}.out"] = header + _normalise(proc.stdout + proc.stderr, work)
        decks = work / "decks"
        if decks.exists():
            for path in sorted(decks.glob("*")):
                result[f"decks/{path.name}"] = _normalise_file(path.read_text(encoding="utf-8"), work)
        for rel in case.files:
            path = work / rel
            result[rel] = (_normalise_file(path.read_text(encoding="utf-8"), work)
                           if path.exists() else "<missing>\n")
        db = work / "scratch.db"
        if db.exists():
            result[DB_DUMP] = dump_database(db, work)
    return result


def _run_all(selected: list[Case], jobs: int):
    """Yield (case, results) in case order, running cases in parallel."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_case, case) for case in selected]
        for case, fut in zip(selected, futures):
            yield case, fut.result()


def _write_snapshot(dest: Path, selected: list[Case], jobs: int) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for n, (case, results) in enumerate(_run_all(selected, jobs), 1):
        print(f"[{n}/{len(selected)}] {case.name}", flush=True)
        for rel, content in results.items():
            path = dest / case.name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def _read_snapshot(case_dir: Path) -> dict[str, str]:
    if not case_dir.exists():
        return {}
    return {
        str(p.relative_to(case_dir)): p.read_text(encoding="utf-8")
        for p in sorted(case_dir.rglob("*")) if p.is_file()
    }


# ---------------------------------------------------------------------------
# Documented, intentional behaviour changes relative to the original baseline.
# `compare --documented` accepts exactly these differences and nothing else.
# Keep in sync with tests/golden/CHANGES.md.
# ---------------------------------------------------------------------------

@dataclass
class DocumentedChange:
    id: str
    summary: str
    # Regex rewrites applied to the *current* console output (step*.out) to
    # reconstruct what the baseline printed.
    rewrites: list[tuple[str, str]] = field(default_factory=list)
    # Regex normalisations applied to BOTH sides (all files) before comparing:
    # masks values a fix legitimately changes (e.g. prices) so the rest of the
    # case is still verified byte-for-byte.
    normalize: list[tuple[str, str]] = field(default_factory=list)
    # Cases whose baseline output is superseded entirely by this change.
    superseded: list[str] = field(default_factory=list)
    # Cases this change may alter beyond the rules above (reported as "changed").
    affects: Callable[[Case], bool] | None = None


def _has_step(case: Case, pred: Callable[[list[str]], bool]) -> bool:
    return any(pred(step) for step in case.steps)


DOCUMENTED_CHANGES: list[DocumentedChange] = [
    DocumentedChange(
        "C1",
        "`build` stores every deck in the SQLite database and prints its id: "
        "'Deck saved → <file> (deck #N)'.",
        rewrites=[(r"(?m)^(Deck saved → .*) \(deck #\d+\)$", r"\1")],
    ),
    DocumentedChange(
        "C2",
        "`list decks` reads the deck database instead of scanning decks/*.txt: "
        "new layout (id, name, colors, size, price, source, date, file) and a new "
        "empty message.",
        superseded=["list-decks-empty", "list-decks-after-builds"],
    ),
    DocumentedChange(
        "C3",
        "A deterministic dump of the deck database is recorded per case (db-dump.txt); "
        "the baseline has none, so it is ignored there.",
    ),
    DocumentedChange(
        "C4",
        "Legacy decks/*.txt files are imported into the database once, on first use of "
        "the deck library (new cases only).",
    ),
    DocumentedChange(
        "C5",
        "`build -f <unknown>` fails up front with a clear message (new case only).",
    ),
    DocumentedChange("C6", "New `decks` command group (new cases only)."),
    DocumentedChange(
        "C7",
        "LLM anti-repetition reads previous decks from the database (new case only).",
    ),
    DocumentedChange(
        "D1",
        "`validate` counts quantities (\"15 Plains\" = 15), checks that the commander can be "
        "a commander and that partners can pair, accepts --partner, reports unknown cards.",
        superseded=["validate-precon-first-flight", "validate-precon-grave-danger",
                    "validate-zaxara-decklist"],
    ),
    DocumentedChange(
        "D2",
        "One price rule everywhere (nonfoil, else foil, else etched) and the budget covers all "
        "100 cards including the commander(s): 'Est. price' and the budget lines change; "
        "--budget builds may swap different cards.",
        normalize=[
            (r"Est\. price: \$[\d.]+", "Est. price: $<PRICE>"),
            (r"(Budget: deck fits at )\$[\d.]+", r"\1$<PRICE>"),
            (r"(— best is )\$[\d.]+", r"\1$<PRICE>"),
            (r"\(\$(?:[\d.]+|\?), EDHREC", "($<PRICE>, EDHREC"),
        ],
        affects=lambda case: _has_step(case, lambda st: "--budget" in st),
    ),
    DocumentedChange(
        "D3",
        "Power brackets work offline: when Commander Spellbook is unreachable (or "
        "COMMANDERAI_OFFLINE=1) game changers, extra turns and mass land denial are excluded "
        "from local card data, with a notice that combos were not checked.",
        affects=lambda case: _has_step(
            case, lambda st: any(a in ("-b", "--bracket") for a in st)
            and st[st.index("-b" if "-b" in st else "--bracket") + 1] != "5"),
    ),
    DocumentedChange(
        "D5",
        "`tokens`: predefined artifact tokens get their type ('Artifact — Food'), 'tapped' is "
        "no longer part of a token name (merging duplicate Zombie tokens), and copy tokens "
        "are listed as 'Copy of a permanent'.",
        affects=lambda case: _has_step(case, lambda st: st[:1] == ["tokens"]),
    ),
    DocumentedChange(
        "D6",
        "COMMANDERAI_OFFLINE=1 disables all network calls (brackets offline, no LLM call, "
        "update-data refuses) — new case only.",
    ),
]


def _apply_rewrites(results: dict[str, str]) -> dict[str, str]:
    out = {}
    for rel, content in results.items():
        if rel.endswith(".out"):
            for change in DOCUMENTED_CHANGES:
                for pattern, repl in change.rewrites:
                    content = re.sub(pattern, repl, content)
        out[rel] = content
    return out


def _apply_normalize(results: dict[str, str]) -> dict[str, str]:
    out = {}
    for rel, content in results.items():
        for change in DOCUMENTED_CHANGES:
            for pattern, repl in change.normalize:
                content = re.sub(pattern, repl, content)
        out[rel] = content
    return out


def _affecting(case: Case) -> list[str]:
    return [
        ch.id for ch in DOCUMENTED_CHANGES
        if case.name in ch.superseded or (ch.affects is not None and ch.affects(case))
    ]


def _print_diff(case: Case, expected: dict[str, str], actual: dict[str, str]) -> None:
    for rel in sorted(set(expected) | set(actual)):
        a, b = expected.get(rel), actual.get(rel)
        if a == b:
            continue
        if a is None or b is None:
            print(f"    {'extra' if a is None else 'missing'} file: {rel}")
            continue
        diff = difflib.unified_diff(
            a.splitlines(), b.splitlines(),
            f"expected/{case.name}/{rel}", f"actual/{case.name}/{rel}", lineterm="",
        )
        for line in diff:
            print("    " + line)


def compare(against: Path, selected: list[Case], verbose: bool = True, jobs: int = 1,
            documented: bool = False) -> int:
    counts = {"ok": 0, "ok-documented": 0, "changed": 0, "new": 0, "DIFF": 0}
    for case, actual in _run_all(selected, jobs):
        expected = _read_snapshot(against / case.name)
        if not expected:
            if documented:
                counts["new"] += 1
                print(f"new      {case.name} (not in baseline; covered by tests/golden/expected)")
                continue
            counts["DIFF"] += 1
            print(f"MISSING  {case.name} (no snapshot)")
            continue
        if DB_DUMP not in expected:
            actual.pop(DB_DUMP, None)
        if expected == actual:
            counts["ok"] += 1
            print(f"ok       {case.name}", flush=True)
            continue
        if documented:
            exp_n = _apply_normalize(expected)
            act_n = _apply_normalize(_apply_rewrites(actual))
            if exp_n == act_n:
                counts["ok-documented"] += 1
                print(f"ok*      {case.name} (identical apart from documented changes)", flush=True)
                continue
            ids = _affecting(case)
            if ids:
                counts["changed"] += 1
                print(f"changed  {case.name} (documented change {', '.join(ids)})", flush=True)
                continue
            counts["DIFF"] += 1
            print(f"DIFF     {case.name}", flush=True)
            if verbose:
                _print_diff(case, exp_n, act_n)
            continue
        counts["DIFF"] += 1
        print(f"DIFF     {case.name}", flush=True)
        if verbose:
            _print_diff(case, expected, actual)

    total = len(selected)
    print()
    if documented:
        print(f"Against {against}:")
        print(f"  {counts['ok']:4} identical")
        print(f"  {counts['ok-documented']:4} identical apart from documented changes")
        print(f"  {counts['changed']:4} changed by a documented change")
        print(f"  {counts['new']:4} new cases (no baseline)")
        print(f"  {counts['DIFF']:4} UNEXPECTED differences")
    else:
        print(f"{counts['ok']}/{total} cases match {against}")
    return 1 if counts["DIFF"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture", help="write a snapshot of the current behaviour")
    cap.add_argument("--dest", type=Path, default=DEFAULT_SNAPSHOT)
    cap.add_argument("--force-baseline", action="store_true",
                     help="allow overwriting the original baseline (never needed normally)")
    cap.add_argument("-k", help="only cases whose name contains this string")
    cap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    cmp_ = sub.add_parser("compare", help="compare the current behaviour with a snapshot")
    cmp_.add_argument("--against", type=Path, default=None,
                      help="snapshot dir (default: expected/, or baseline/ with --documented)")
    cmp_.add_argument("--documented", action="store_true",
                      help="compare with the original baseline, accepting only documented changes")
    cmp_.add_argument("-k", help="only cases whose name contains this string")
    cmp_.add_argument("-q", "--quiet", action="store_true", help="don't print diffs")
    cmp_.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    sub.add_parser("list", help="list the case names")
    sub.add_parser("changes", help="list the documented behaviour changes")
    args = parser.parse_args()

    all_cases = cases()
    selected = [c for c in all_cases if not getattr(args, "k", None) or args.k in c.name]
    if args.cmd == "list":
        for case in all_cases:
            print(case.name)
        return 0
    if args.cmd == "changes":
        for ch in DOCUMENTED_CHANGES:
            print(f"{ch.id}: {ch.summary}")
            affected = [c.name for c in all_cases
                        if c.name in ch.superseded or (ch.affects and ch.affects(c))]
            if affected:
                print(f"      may change {len(affected)} case(s): {', '.join(affected)}")
        return 0
    if args.cmd == "capture":
        if args.dest.resolve() == BASELINE.resolve() and not args.force_baseline:
            print("Refusing to overwrite the original baseline (use --force-baseline).")
            return 2
        _write_snapshot(args.dest, selected, args.jobs)
        print(f"Captured {len(selected)} cases → {args.dest}")
        return 0
    against = args.against or (BASELINE if args.documented else DEFAULT_SNAPSHOT)
    return compare(against, selected, verbose=not args.quiet, jobs=args.jobs,
                   documented=args.documented)


if __name__ == "__main__":
    sys.exit(main())
