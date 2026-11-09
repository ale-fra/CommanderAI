#!/usr/bin/env python3
"""Differential test: original 0.7.0 CLI vs the current CLI, side by side.

The golden harness can only exercise what the offline data allows. This script
covers the remaining paths by injecting identical fakes into BOTH
implementations and comparing their console output, exit codes and deck files:

- partner / Background commanders (synthetic cards added to the catalog),
- Commander Spellbook bracket results (fake exclusions, combos, prioritised cards),
- Claude responses (success with duplicates/upgrade swaps, failure, prior decks).

The original implementation is tests/golden/reference/cli_0_7_0.py. Documented
behaviour changes (see tests/golden/CHANGES.md: C1 deck id, C4 migration notice,
D2 prices) are normalised before comparing; budget behaviour (D2) is covered by the
golden cases and unit tests instead.

Usage:  python scripts/difftest.py        (exit code 0 = all cases identical)
"""
import difflib
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(COMMANDERAI_CACHE=str(ROOT/"tests/fixtures/integration/catalog"), COLUMNS="120", NO_COLOR="1", TERM="dumb", ANTHROPIC_API_KEY="", COMMANDERAI_OFFLINE="0")
from rich.console import Console
from typer.testing import CliRunner

import commanderai.deckbuilder.bracket as bracket_mod
from commanderai.data.card_index import CardIndex
from commanderai.data.scryfall import load_catalog_data
from commanderai.deckbuilder.bracket import BracketResult
from commanderai.models import Card, DeckPick

spec = importlib.util.spec_from_file_location("cli_original", ROOT / "tests/golden/reference/cli_0_7_0.py")
orig = importlib.util.module_from_spec(spec); spec.loader.exec_module(orig)
import commanderai.cli.commands as new
import commanderai.services.build as buildmod
import commanderai.services.context as ctxmod

# ---- synthetic catalog: real cards + partner commanders -----------------------
cards, non_legal = load_catalog_data(ROOT/"tests/fixtures/integration/catalog"/"oracle_cards.json")
def cmdr(name, colors, text, kw, tl="Legendary Creature — Human Wizard"):
    return Card(name=name, type_line=tl, color_identity=colors, colors=colors, oracle_text=text,
                keywords=kw, edhrec_rank=500, mana_cost="{2}" + "".join(f"{{{c}}}" for c in colors), cmc=2+len(colors),
                prices={"usd": "1.50"})
extra = [
    cmdr("Alpha Partner", ["G","U"], "Partner (You can have two commanders if both have partner.)\nWhenever you create a token, draw a card.", ["Partner"]),
    cmdr("Beta Partner", ["B"], "Partner (You can have two commanders if both have partner.)\nWhenever a creature you control dies, each opponent loses 1 life.", ["Partner"]),
    cmdr("Gamma Chooser", ["R"], "Choose a Background (You can have a Background as a second commander.)\nHaste", ["Choose a Background"]),
    cmdr("Omega Partner", ["G"], "Partner (You can have two commanders if both have partner.)\nTrample", ["Partner"]),
    cmdr("Zeta Partner", ["W"], "Partner (You can have two commanders if both have partner.)\nFlying", ["Partner"]),
    cmdr("Eta Partner", ["U"], "Partner (You can have two commanders if both have partner.)\nWhenever a creature attacks you, draw a card.", ["Partner"]),
    Card(name="Epsilon Background", type_line="Legendary Enchantment — Background", color_identity=["R"], oracle_text="Commander creatures you own have haste.", edhrec_rank=800, prices={"usd":"0.25"}),
    Card(name="Delta Background", type_line="Legendary Enchantment — Background", color_identity=["W"], oracle_text="Commander creatures you own have lifelink.", edhrec_rank=900, prices={"usd":"0.5"}),
]
ALL = cards + extra
def fake_index(*a, **k): return CardIndex(ALL, non_legal_names=non_legal)

# ---- fake bracket --------------------------------------------------------------
def fake_check_bracket(commander, candidates, bracket, partner=None, offline=False):
    r = BracketResult()
    names = [c.name for c in candidates]
    excl = names[:18]
    r.excluded_cards = [(n, "game changer") for n in excl]
    r.excluded_combos = [([names[20], names[21]], "bracket R, infinite mana")] * 6
    r.allowed_names = set(names) - set(excl)
    r.prioritized_names = set(names[25:28])
    return r

# ---- fake LLM ------------------------------------------------------------------
def fake_llm_build(commander, candidates, land_count, extra_instructions="", owned_names=None, **kw):
    flat = [sc for s in candidates.values() for sc in s]
    picks = [DeckPick(card=sc.card, slot=sc.slot, reason="llm pick") for sc in flat[:40]]
    picks.append(DeckPick(card=flat[0].card, slot=flat[0].slot, reason="dup"))  # duplicate -> validation warning
    upgrades = [flat[45].card.name, flat[46].card.name, "Some Unowned Card", flat[0].card.name]
    return picks, "A fake strategy summary.", upgrades

def fake_llm_fail(*a, **k): raise RuntimeError("boom (fake)")

def install(llm):
    orig.load_cards = lambda *a, **k: ALL
    orig.load_non_legal_names = lambda *a, **k: non_legal
    ctxmod.load_catalog = fake_index
    bracket_mod.check_bracket = fake_check_bracket
    orig.llm_build = llm
    buildmod.llm_build = llm

COLL = (ROOT/"tests/fixtures/integration/collections/expanded-collection.txt").read_text() + \
    "\n1 Alpha Partner\n1 Beta Partner\n1 Omega Partner\n1 Gamma Chooser\n1 Epsilon Background\n1 Delta Background\n1 Arcane Signat\n1 Totally Madeup Card\n"
SMALL = "\n".join(l for l in (ROOT/"tests/fixtures/integration/collections/precons/first-flight.txt").read_text().splitlines()) + "\n1 Alpha Partner\n1 Beta Partner\n1 Zeta Partner\n1 Eta Partner\n"

CASES = [
    ("partner-explicit", ["build", "-C", "Alpha Partner", "-P", "Beta Partner", "--no-llm", "-v"], fake_llm_build, COLL),
    ("partner-tip", ["build", "-C", "Alpha Partner", "--no-llm"], fake_llm_build, COLL),
    ("partner-auto", ["build", "--theme", "tokens", "--colors", "simic", "--no-llm"], fake_llm_build, COLL),
    ("background-auto", ["build", "--colors", "R", "--theme", "lifegain", "--no-llm"], fake_llm_build, COLL),
    ("background-explicit-arch", ["build", "-C", "Gamma Chooser", "-P", "Delta Background", "--no-llm", "-f", "archidekt"], fake_llm_build, COLL),
    ("bracket-fake", ["build", "-C", "Zaxara, the Exemplary", "--no-llm", "-b", "2"], fake_llm_build, COLL),
    ("bracket3-partner", ["build", "-C", "Alpha Partner", "-P", "Beta Partner", "--no-llm", "-b", "3"], fake_llm_build, COLL),
    ("llm-success", ["build", "-C", "Zaxara, the Exemplary", "-v"], fake_llm_build, COLL),
    ("llm-success-bracket", ["build", "-C", "Muldrotha, the Gravetide", "-b", "2"], fake_llm_build, COLL),
    ("llm-fail", ["build", "-C", "Zaxara, the Exemplary"], fake_llm_fail, COLL),
    ("llm-variety-prior", ["build", "-C", "Zaxara, the Exemplary", "--seed", "3"], fake_llm_build, COLL),
    ("small-partner-shortfall", ["build", "-C", "Alpha Partner", "-P", "Beta Partner", "--no-llm"], fake_llm_build, SMALL),
    ("small-partner-shortfall-wu", ["build", "-C", "Zeta Partner", "-P", "Eta Partner", "--no-llm"], fake_llm_build, SMALL),
    ("partner-auto-variety", ["build", "--theme", "tokens", "--colors", "simic", "--no-llm", "--seed", "8"], fake_llm_build, COLL),
    ("small-llm-shortfall", ["build", "-C", "Fixture Flight Commander"], fake_llm_build, SMALL),
    ("list-commanders-partners", ["list", "commanders"], fake_llm_build, COLL),
    ("suggest-commanders-partners", ["suggest-commanders", "--top", "30"], fake_llm_build, COLL),
]

def run(module, args, coll_text, workdir):
    (workdir/"decks").mkdir(exist_ok=True)
    coll = workdir/"coll.txt"; coll.write_text(coll_text)
    if args[0] in ("build", "list", "suggest-commanders") and "-c" not in args:
        args = args[:1] + ["-c", str(coll)] + args[1:] if args[0] != "list" else args + ["-c", str(coll)]
    cwd = os.getcwd(); os.chdir(workdir)
    os.environ["COMMANDERAI_DECKS_DIR"] = "decks"
    os.environ["COMMANDERAI_DB"] = str(workdir / "scratch.db")
    orig.DECKS_DIR = Path("decks")
    try:
        module.console = Console(width=120, no_color=True)
        res = CliRunner().invoke(module.app, args)
    finally:
        os.chdir(cwd)
    out = "\n".join(l.rstrip() for l in res.output.splitlines() if not (l.strip() and l.strip()[0] in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"))
    files = {p.name: p.read_text() for p in sorted((workdir/"decks").glob("*"))}
    if res.exception and not isinstance(res.exception, SystemExit):
        out += f"\nEXCEPTION: {res.exception!r}"
    out = out.replace(str(workdir), "<W>")
    # Documented change C1: build prints the database id of the stored deck.
    out = re.sub(r"(?m)^(Deck saved → .*) \(deck #\d+\)$", r"\1", out)
    # Documented change C4: legacy deck files are migrated into the database once.
    out = re.sub(r"(?m)^Imported \d+ legacy deck file\(s\) from .*\n?", "", out)
    # Documented change D2: one price rule (commanders, foil fallback) — mask prices.
    out = re.sub(r"Est\. price: \$[\d.]+", "Est. price: $<PRICE>", out)
    files = {k: re.sub(r"Est\. price: \$[\d.]+", "Est. price: $<PRICE>", v) for k, v in files.items()}
    return res.exit_code, out, files

fails = 0
print("Differential test: original 0.7.0 CLI vs current CLI (with injected fakes)\n")
for name, args, llm, coll in CASES:
    install(llm)
    results = []
    for module in (orig, new):
        with tempfile.TemporaryDirectory() as t:
            w = Path(t)
            if name == "llm-variety-prior":   # pre-existing decks for the same commander
                (w/"decks").mkdir()
                (w/"decks"/"zaxara__the_exemplary.txt").write_text("1 Zaxara, the Exemplary [Commander]\n1 Sol Ring [Ramp]\n1 Rhystic Study [Draw]\n")
            results.append(run(module, list(args), coll, w))
    a, b = results
    same = a == b
    fails += not same
    print(("ok   " if same else "DIFF ") + name + f"  (exit {a[0]}, {len(a[1].splitlines())} lines, files {list(a[2])})")
    if not same:
        for x, y, label in ((a[1], b[1], "output"),):
            print("\n".join(difflib.unified_diff(x.splitlines(), y.splitlines(), "orig", "new", lineterm="")))
        if a[2] != b[2]: print("  files differ", a[0], b[0])
        if a[0] != b[0]: print("  exit differ", a[0], b[0])
print(f"\n{len(CASES)-fails}/{len(CASES)} identical")

# ---- coverage of target paths (on the new implementation's outputs) ----------
ALL_OUT = []
for name, args, llm, coll in CASES:
    install(llm)
    with tempfile.TemporaryDirectory() as t:
        w = Path(t)
        if name == "llm-variety-prior":
            (w/"decks").mkdir(); (w/"decks"/"zaxara__the_exemplary.txt").write_text("1 Zaxara, the Exemplary [Commander]\n1 Sol Ring [Ramp]\n")
        ALL_OUT.append(run(new, list(args), coll, w)[1])
blob = "\n".join(ALL_OUT)
print("\nPath coverage (occurrences in the current CLI's output; every count must be > 0):")
missing = 0
for pat in ["Validation warnings", "Backfilled", " ~ '", "not found$", "Auto-selected partner",
            "Commanders:", "Tip: this commander", "Bracket .* excluded", "\\.\\.\\. and .* more", "Excluded .* combos",
            "Prioritized", "Swapped in", "prior deck", "LLM failed", "Strategy:", "Upgrade Suggestions", "Partner\\)"]:
    n = len(re.findall(pat, blob, re.MULTILINE))
    missing += n == 0
    print(f"  {pat:28} {n}")
sys.exit(1 if fails or missing else 0)
