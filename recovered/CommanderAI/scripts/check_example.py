#!/usr/bin/env python3
"""Re-test a deck you generated earlier (e.g. before the refactor).

Re-runs ``commanderai build`` with the same arguments in a clean scratch
directory (offline catalog, no API key, empty deck database) and compares:

1. the deck file it writes with your stored deck file — must be IDENTICAL;
2. optionally (``--log``) the console output with a stored console log —
   compared after ignoring only: spinner lines, the '(deck #N)' suffix added by
   the deck database (documented change C1) and the directory in 'Deck saved →'.

Examples:
    # you saved decks/zaxara__the_exemplary.txt from:
    #   commanderai build -C "Zaxara, the Exemplary" --no-llm
    .venv/bin/python scripts/check_example.py ~/saved/zaxara__the_exemplary.txt \\
        -- -C "Zaxara, the Exemplary" --no-llm

    # also compare the console output you captured with `... | tee zaxara.log`
    .venv/bin/python scripts/check_example.py ~/saved/zaxara.txt --log ~/saved/zaxara.log \\
        -- -C "Zaxara, the Exemplary" --no-llm

Everything after ``--`` is passed to ``commanderai build`` unchanged. Relative
paths in those arguments (e.g. ``-c my_collection.txt``) are resolved from the
directory you run this script in. Exit code 0 = identical.

Notes:
- The collection defaults to commanderai-sample/expanded-collection.txt (the
  bundled offline sample). Pass ``-c`` in the build arguments if your example
  used another collection.
- Builds with ``--variety`` but no ``--seed`` are random and cannot be
  reproduced; builds with ``--seed`` can.
- Examples built before the phase-D fixes with ``--budget`` or ``--bracket``
  (1-4) can legitimately differ: see tests/golden/CHANGES.md (D2, D3).
- Console logs depend on terminal width; use ``--columns`` to match the width
  of the terminal the log was captured in (default 120; a non-interactive
  `tee` capture usually used 80).
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPINNER = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
PATH_OPTIONS = {"-c", "--collection", "-o", "--output"}


def normalise_log(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s and s[0] in SPINNER:
            continue
        line = line.rstrip()
        if line.startswith("Deck saved → "):
            line = re.sub(r" \(deck #\d+\)$", "", line)               # documented change C1
            line = "Deck saved → " + re.split(r"[/\\]", line[len("Deck saved → "):])[-1]
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return out


def absolutise(args: list[str]) -> list[str]:
    """Make path arguments absolute so they still work from the scratch dir."""
    fixed, expect_path = [], False
    for a in args:
        if expect_path:
            fixed.append(str(Path(a).expanduser().resolve()))
            expect_path = False
            continue
        if a in PATH_OPTIONS:
            expect_path = True
        elif "=" in a and a.split("=", 1)[0] in PATH_OPTIONS:
            opt, val = a.split("=", 1)
            a = f"{opt}={Path(val).expanduser().resolve()}"
        fixed.append(a)
    return fixed


def report(title: str, expected: list[str], actual: list[str], a_name: str, b_name: str) -> bool:
    if expected == actual:
        print(f"\033[32m{title}: IDENTICAL\033[0m")
        return True
    print(f"\033[31m{title}: DIFFERENT\033[0m")
    for line in difflib.unified_diff(expected, actual, a_name, b_name, lineterm=""):
        print("  " + line)
    return False


def main() -> int:
    argv = sys.argv[1:]
    if "--" not in argv:
        print(__doc__)
        print("error: put the build arguments after '--'", file=sys.stderr)
        return 2
    split = argv.index("--")
    parser = argparse.ArgumentParser(description="Re-test a stored deck example.")
    parser.add_argument("deck_file", type=Path, help="the deck file you stored earlier")
    parser.add_argument("--log", type=Path, help="stored console output of that build (optional)")
    parser.add_argument("--columns", type=int, default=120, help="terminal width for the console comparison")
    args = parser.parse_args(argv[:split])
    build_args = absolutise(argv[split + 1:])

    if not args.deck_file.exists():
        print(f"error: {args.deck_file} not found", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="cai-example-") as tmp:
        work = Path(tmp)
        env = dict(os.environ)
        env.update({
            "PYTHONPATH": str(ROOT / "src"),
            "COMMANDERAI_CACHE": str(ROOT / "offline-data"),
            "COMMANDERAI_COLLECTION": str(ROOT / "commanderai-sample" / "expanded-collection.txt"),
            "COMMANDERAI_DECKS_DIR": "decks",
            "COMMANDERAI_DB": "scratch.db",
            "ANTHROPIC_API_KEY": "",
            "COMMANDERAI_OFFLINE": "1",
            "COLUMNS": str(args.columns),
            "NO_COLOR": "1",
            "TERM": "dumb",
        })
        cmd = [sys.executable, "-m", "commanderai.cli", "build", *build_args]
        print("Running: commanderai build " + " ".join(build_args))
        proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, check=False)
        print(f"Exit code: {proc.returncode}\n")

        produced = None
        if "-o" in build_args or "--output" in build_args:
            opt = "-o" if "-o" in build_args else "--output"
            produced = Path(build_args[build_args.index(opt) + 1])
        else:
            files = sorted((work / "decks").glob("*.txt")) if (work / "decks").exists() else []
            produced = files[0] if len(files) == 1 else None
        if produced is None or not produced.exists():
            print("\033[31mThe build did not produce a deck file.\033[0m Console output:\n")
            print(proc.stdout + proc.stderr)
            return 1

        ok = report(
            "Deck file",
            args.deck_file.read_text(encoding="utf-8").splitlines(),
            produced.read_text(encoding="utf-8").splitlines(),
            f"stored/{args.deck_file.name}", f"rebuilt/{produced.name}",
        )
        if args.log:
            ok &= report(
                "Console output",
                normalise_log(args.log.read_text(encoding="utf-8")),
                normalise_log(proc.stdout + proc.stderr),
                f"stored/{args.log.name}", "rebuilt/console",
            )
        else:
            print("(console output not compared — pass --log FILE to compare it too)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
