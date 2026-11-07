import re
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from commanderai.collection.matcher import get_unique_cards, match_collection
from commanderai.collection.parser import aggregate_entries, convert_to_text, parse_collection
from commanderai.config import DECKS_DIR, DEFAULT_COLLECTION, DEFAULT_LAND_COUNT, SLOT_QUOTAS
from commanderai.data.card_index import CardIndex
from commanderai.data.scryfall import download_bulk_data, load_cards, load_non_legal_names
from commanderai.deckbuilder.budget import (
    enforce_budget,
    filter_candidates_by_budget,
)
from commanderai.deckbuilder.candidates import build_candidates, heuristic_pick
from commanderai.deckbuilder.llm_picker import llm_build
from commanderai.deckbuilder.mana_base import build_mana_base
from commanderai.deckbuilder.rules import is_legal_commander, validate_deck
from commanderai.deckbuilder.slots import classify_card
from commanderai.deckbuilder.colors import (
    COLOR_NAMES,
    color_name,
    format_colors,
    resolve_colors,
    wubrg_sort,
)
from commanderai.deckbuilder.partner import (
    can_partner,
    combined_identity,
    partner_ability,
)
from commanderai.deckbuilder.themes import (
    ALIASES,
    TRIBES,
    apply_theme_quotas,
    archetype_names,
    resolve_theme,
    theme_hits,
)
from commanderai.deckbuilder.variety import (
    make_rng,
    resolve_seed,
    softmax_weights,
    weighted_sample_without_replacement,
)
from commanderai.models import Deck, DeckPick, DeckSlot, ScoredCard
from commanderai.output.export import export_deck
from commanderai.output.formatter import format_deck

app = typer.Typer(name="commanderai", help="AI-powered Commander deck builder")
console = Console()


def _load_index() -> CardIndex:
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("Loading card database...", total=None)
        cards = load_cards()
        non_legal = load_non_legal_names()
    console.print(f"[dim]Loaded {len(cards)} Commander-legal cards[/dim]")
    return CardIndex(cards, non_legal_names=non_legal)


def _resolve_theme_or_exit(theme: Optional[str]) -> Optional[str]:
    if not theme:
        return None
    canonical = resolve_theme(theme)
    if canonical is None:
        console.print(
            f"[red]Unknown theme '{theme}'.[/red]\n"
            f"[dim]Archetypes: {', '.join(archetype_names())}[/dim]\n"
            f"[dim]Also accepts tribes (elf, goblin, dragon, sliver...) and aliases "
            f"(go-wide, storm, bogles, tron, death-and-taxes...).[/dim]"
        )
        raise typer.Exit(1)
    return canonical


def _resolve_colors_or_exit(colors: Optional[str]) -> "set[str] | None":
    if not colors:
        return None
    resolved = resolve_colors(colors)
    if resolved is None:
        console.print(
            f"[red]Unknown colors '{colors}'. Use WUBRG letters (e.g. WUB) or a "
            f"combination name (e.g. esper, jund, azorius, five-color).[/red]"
        )
        raise typer.Exit(1)
    return resolved


def _auto_select_commander(
    collection_cards: "list",
    theme: Optional[str],
    color_filter: "set[str] | None",
    rng: "random.Random | None",
    variety: float,
) -> "tuple | None":
    """Pick the best-fit owned commander for a theme/colors when none is given.

    Scores each legal commander you own by on-theme card support in its colors,
    its own theme fit, and EDHREC rank. Returns (commander, on_theme_support,
    theme_fit) or None if no eligible commander exists.
    """
    legal = [c for c in collection_cards if is_legal_commander(c)]
    if color_filter is not None:
        legal = [c for c in legal if set(c.color_identity).issubset(color_filter)]
    if not legal:
        return None

    # Precompute which owned cards are on-theme (for support counting).
    if theme:
        on_theme = [
            c for c in collection_cards
            if theme_hits(theme, c.oracle_text, c.type_line) > 0
        ]
    else:
        on_theme = collection_cards

    scored: list[tuple] = []
    for cmdr in legal:
        identity = set(cmdr.color_identity)
        support = sum(
            1 for c in on_theme
            if c.name != cmdr.name and set(c.color_identity).issubset(identity)
        )
        fit = theme_hits(theme, cmdr.oracle_text, cmdr.type_line) if theme else 0
        rank_bonus = max(0.0, 100 - (cmdr.edhrec_rank or 99999) / 300)
        weight = fit * 60 + support + rank_bonus
        scored.append((cmdr, support, fit, weight))

    scored.sort(key=lambda x: x[3], reverse=True)

    if variety > 0 and rng is not None and len(scored) > 1:
        pool = scored[: max(8, 1)]
        weights = softmax_weights([x[3] for x in pool], variety)
        chosen = weighted_sample_without_replacement(rng, pool, weights, 1)[0]
    else:
        chosen = scored[0]
    return chosen[0], chosen[1], chosen[2]


def _auto_select_partner(
    commander,
    collection_cards: "list",
    theme: Optional[str],
    color_filter: "set[str] | None",
    rng: "random.Random | None",
    variety: float,
):
    """Find the best owned partner for a commander that wants one, or None."""
    if not partner_ability(commander).can_take_partner:
        return None

    primary_colors = set(commander.color_identity)
    eligible = []
    for c in collection_cards:
        if c.name == commander.name or not can_partner(commander, c):
            continue
        union = primary_colors | set(c.color_identity)
        if color_filter is not None and not union.issubset(color_filter):
            continue
        eligible.append(c)
    if not eligible:
        return None

    scored = []
    for c in eligible:
        fit = theme_hits(theme, c.oracle_text, c.type_line) if theme else 0
        new_colors = len(set(c.color_identity) - primary_colors)
        rank_bonus = max(0.0, 100 - (c.edhrec_rank or 99999) / 300)
        weight = fit * 50 + new_colors * 15 + rank_bonus
        scored.append((c, weight))
    scored.sort(key=lambda x: x[1], reverse=True)

    if variety > 0 and rng is not None and len(scored) > 1:
        pool = scored[:8]
        weights = softmax_weights([w for _, w in pool], variety)
        return weighted_sample_without_replacement(rng, pool, weights, 1)[0][0]
    return scored[0][0]


def _setup_variety(variety: float, seed: Optional[int]) -> tuple[float, "random.Random | None"]:
    """Resolve variety + RNG. Passing --seed alone implies moderate variety.

    Prints the seed used so any variety run can be reproduced. Returns
    (effective_variety, rng) where rng is None when fully deterministic.
    """
    import random

    effective = variety
    if seed is not None and variety == 0.0:
        effective = 0.5
    if effective <= 0:
        return 0.0, None
    resolved = resolve_seed(seed)
    console.print(
        f"[dim]Variety {effective:.2f} (seed {resolved} — reuse with --seed {resolved})[/dim]"
    )
    return effective, make_rng(resolved)


def _require_collection(path: Path) -> None:
    """Exit with a friendly message if the collection file is missing."""
    if not path.exists():
        console.print(
            f"[red]Collection file not found: {path}[/red]\n"
            f"[dim]Pass --collection/-c <file>, or create the default "
            f"{DEFAULT_COLLECTION} (e.g. via `commanderai convert`).[/dim]"
        )
        raise typer.Exit(1)


_BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


def _safe_deck_name(commander_name: str) -> str:
    return re.sub(r"[^\w\-]", "_", commander_name.split("//")[0].strip()).lower().strip("_")


def _load_prior_decks(commander_name: str) -> list[list[str]]:
    """Best-effort parse of previously-saved decks for this commander.

    Returns a list of non-land card-name lists, used to nudge the LLM toward a
    different build. Handles both the simple/archidekt export and the grouped
    text format (stripping slot tags, mana costs, and verbose reasons).
    """
    safe = _safe_deck_name(commander_name)
    if not DECKS_DIR.exists():
        return []

    decks: list[list[str]] = []
    for path in sorted(DECKS_DIR.glob(f"{safe}*.txt")):
        names: list[str] = []
        for raw in path.read_text().splitlines():
            line = raw.strip()
            m = re.match(r"^\d+x?\s+(.+)$", line)
            if not m:
                continue
            rest = m.group(1).strip()

            tag = None
            tag_match = re.search(r"\s*\[([^\]]+)\]\s*$", rest)
            if tag_match:
                tag = tag_match.group(1)
                rest = rest[: tag_match.start()].strip()
            if tag in ("Land", "Commander"):
                continue

            rest = rest.replace("*CMDR*", "").strip()
            rest = re.split(r"\s+(?:\{|//)", rest, maxsplit=1)[0].strip()
            if not rest or rest in _BASIC_LANDS:
                continue
            names.append(rest)
        if names:
            decks.append(names)
    return decks


@app.command()
def build(
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c", help="Path to collection file"
    ),
    commander_name: Optional[str] = typer.Option(
        None, "--commander", "-C",
        help="Commander card name (omit to auto-pick from --theme/--colors)",
    ),
    partner_name: Optional[str] = typer.Option(
        None, "--partner", "-P",
        help="Second commander (Partner / Background / Doctor's companion etc.)",
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM, use heuristic only"),
    lands: int = typer.Option(DEFAULT_LAND_COUNT, "--lands", help="Number of lands"),
    variety: float = typer.Option(
        0.0, "--variety", min=0.0, max=1.0,
        help="Deck variety 0.0-1.0 (0=deterministic; higher = more variation between builds)",
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Random seed for reproducible variety (implies --variety if unset)"
    ),
    theme: Optional[str] = typer.Option(
        None, "--theme", help="Archetype to lean into (e.g. aristocrats, tokens, dragons)"
    ),
    colors: Optional[str] = typer.Option(
        None, "--colors",
        help="Color filter for auto-pick: WUBRG letters or a name (esper, jund, azorius)",
    ),
    budget: Optional[float] = typer.Option(None, "--budget", help="Max deck price in USD"),
    bracket: Optional[int] = typer.Option(None, "--bracket", "-b", min=1, max=5, help="Power bracket 1-5 (1=casual, 5=cEDH)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write deck to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show scoring details"),
    format: str = typer.Option("text", "--format", "-f", help="Output format"),
):
    """Build a Commander deck from your collection.

    Provide --commander, or omit it and pass --theme and/or --colors to
    auto-pick the best-fit commander you own.
    """
    theme = _resolve_theme_or_exit(theme)
    color_filter = _resolve_colors_or_exit(colors)

    if not commander_name and not theme and color_filter is None:
        console.print(
            "[red]Specify --commander, or --theme/--colors to auto-pick a commander.[/red]"
        )
        raise typer.Exit(1)

    if partner_name and not commander_name:
        console.print("[red]--partner requires --commander.[/red]")
        raise typer.Exit(1)

    effective_variety, rng = _setup_variety(variety, seed)
    synergy_emphasis = 1.0 + effective_variety if effective_variety > 0 else 1.0
    rank_emphasis = 1.0 - 0.4 * effective_variety if effective_variety > 0 else 1.0
    quotas = apply_theme_quotas(SLOT_QUOTAS, theme)

    _require_collection(collection)
    index = _load_index()

    entries = parse_collection(collection)
    if not entries:
        console.print("[red]Error: No cards found in collection file[/red]")
        raise typer.Exit(1)

    match_result = match_collection(entries, index)
    skipped = len(match_result.skipped_tokens)
    unmatched = len(match_result.unmatched)
    status_parts = [f"[green]Matched {len(match_result.matched)} cards[/green]"]
    if skipped:
        status_parts.append(f"[dim]{skipped} tokens/special skipped[/dim]")
    if unmatched:
        status_parts.append(f"[dim]{unmatched} unmatched[/dim]")
    console.print(" | ".join(status_parts))

    if match_result.fuzzy_matched:
        for original, corrected in match_result.fuzzy_matched[:5]:
            console.print(f"  [yellow]~[/yellow] '{original}' → '{corrected}'")

    if match_result.unmatched and verbose:
        for name in match_result.unmatched[:10]:
            console.print(f"  [red]✗[/red] '{name}' not found")

    collection_cards = get_unique_cards(match_result.matched)
    owned_names = {c.name for c in collection_cards}
    owned_names_lower = {n.lower() for n in owned_names}

    if len(collection_cards) < 20:
        console.print(
            f"[red]Collection too small ({len(collection_cards)} cards). "
            f"Need at least ~60+ cards in commander's colors to build a playable deck.[/red]"
        )
        raise typer.Exit(1)

    if commander_name:
        commander = index.get(commander_name)
        if not commander:
            console.print(f"[red]Commander '{commander_name}' not found[/red]")
            raise typer.Exit(1)
        if not is_legal_commander(commander):
            console.print(f"[red]'{commander.name}' is not a legal commander[/red]")
            raise typer.Exit(1)
    else:
        picked = _auto_select_commander(
            collection_cards, theme, color_filter, rng, effective_variety
        )
        if not picked:
            criteria = []
            if theme:
                criteria.append(f"theme '{theme}'")
            if color_filter is not None:
                criteria.append(f"colors {color_name(color_filter)}")
            console.print(
                f"[red]No legal commander in your collection matches "
                f"{' + '.join(criteria) or 'the given filters'}.[/red]"
            )
            raise typer.Exit(1)
        commander, support, fit = picked
        reason = []
        if theme:
            reason.append(f"{support} on-theme cards in colors")
            if fit:
                reason.append(f"commander matches theme ({fit})")
        else:
            reason.append(f"{support} supporting cards")
        console.print(
            f"[green]Auto-selected commander:[/green] {commander.name} "
            f"[{format_colors(commander.color_identity)}] — {', '.join(reason)}"
        )

    # Resolve / auto-pick a partner (second commander).
    partner = None
    if partner_name:
        partner = index.get(partner_name)
        if not partner:
            console.print(f"[red]Partner '{partner_name}' not found[/red]")
            raise typer.Exit(1)
        if not can_partner(commander, partner):
            console.print(
                f"[red]'{commander.name}' and '{partner.name}' can't be partners. "
                f"They need matching Partner, Partner with, Friends forever, "
                f"Choose a Background + Background, or Doctor's companion + Doctor.[/red]"
            )
            raise typer.Exit(1)
    elif not commander_name:
        # Auto-pick mode: if the chosen commander wants a partner, find the best one owned.
        partner = _auto_select_partner(
            commander, collection_cards, theme, color_filter, rng, effective_variety
        )
        if partner:
            console.print(
                f"[green]Auto-selected partner:[/green] {partner.name} "
                f"[{format_colors(partner.color_identity)}]"
            )
    else:
        # Explicit commander with no --partner: hint if it wants one.
        if partner_ability(commander).can_take_partner:
            console.print(
                "[dim]Tip: this commander can have a partner — pass --partner "
                "\"Name\" to build a two-commander deck.[/dim]"
            )

    if partner:
        identity = combined_identity(commander, partner)
        console.print(
            f"\n[bold]Commanders:[/bold] {commander.name} + {partner.name} "
            f"[{format_colors(identity)}]"
        )
        for c in (commander, partner):
            console.print(f"[dim]{c.name}: {c.oracle_text}[/dim]")
        console.print()
    else:
        console.print(f"\n[bold]Commander:[/bold] {commander.name} — {commander.type_line}")
        console.print(f"[dim]{commander.oracle_text}[/dim]\n")

    commander_others = 99 if partner is None else 98
    num_commanders = 100 - commander_others

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("Analyzing candidates...", total=None)
        candidates = build_candidates(
            collection_cards, commander,
            theme=theme, synergy_emphasis=synergy_emphasis, rank_emphasis=rank_emphasis,
            partner=partner, quotas=quotas,
        )

    if theme:
        console.print(f"[dim]Theme: leaning into '{theme}'[/dim]")
        changed = {
            s: f"{SLOT_QUOTAS[s]}→{quotas[s]}"
            for s in SLOT_QUOTAS
            if s != "LAND" and quotas.get(s) != SLOT_QUOTAS.get(s)
        }
        if changed:
            console.print(
                "[dim]Role mix adjusted: "
                + ", ".join(f"{s} {v}" for s, v in changed.items())
                + "[/dim]"
            )

    total_candidates = sum(len(v) for v in candidates.values() if v)
    console.print(f"[dim]Found {total_candidates} candidate cards across all slots[/dim]")

    if budget is not None:
        candidates, removed = filter_candidates_by_budget(candidates, budget)
        if removed:
            console.print(
                f"[dim]Budget ${budget:.2f}: dropped {removed} cards priced above budget[/dim]"
            )
        total_candidates = sum(len(v) for v in candidates.values() if v)

    bracket_info = ""
    bracket_result = None
    if bracket and bracket < 5:
        from commanderai.deckbuilder.bracket import check_bracket

        all_candidate_cards = [sc.card for scored_list in candidates.values() for sc in scored_list]
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            progress.add_task(f"Checking bracket {bracket} constraints (Commander Spellbook)...", total=None)
            bracket_result = check_bracket(commander, all_candidate_cards, bracket)

        if bracket_result.excluded_cards:
            console.print(f"\n[yellow]Bracket {bracket} — excluded {len(bracket_result.excluded_cards)} cards:[/yellow]")
            for name, reason in bracket_result.excluded_cards[:15]:
                console.print(f"  [red]✗[/red] {name} ({reason})")
            if len(bracket_result.excluded_cards) > 15:
                console.print(f"  [dim]... and {len(bracket_result.excluded_cards) - 15} more[/dim]")

        if bracket_result.excluded_combos:
            console.print(f"[yellow]Excluded {len(bracket_result.excluded_combos)} combos:[/yellow]")
            for combo_cards, reason in bracket_result.excluded_combos[:5]:
                console.print(f"  [red]✗[/red] {' + '.join(combo_cards)} ({reason})")

        for slot in candidates:
            candidates[slot] = [
                sc for sc in candidates[slot]
                if sc.card.name in bracket_result.allowed_names
            ]

        if bracket_result.prioritized_names:
            for slot in candidates:
                for sc in candidates[slot]:
                    if sc.card.name in bracket_result.prioritized_names:
                        sc.score += 50
                candidates[slot].sort(key=lambda sc: sc.score, reverse=True)
            console.print(
                f"[green]Prioritized {len(bracket_result.prioritized_names)} "
                f"high-value cards within bracket limits[/green]"
            )

        new_total = sum(len(v) for v in candidates.values() if v)
        console.print(f"[dim]{new_total} candidates remaining after bracket filter[/dim]\n")
        bracket_info = (
            f"IMPORTANT: This deck must be bracket {bracket} (1=most casual, 5=cEDH). "
            f"Do NOT include infinite combos or two-card win conditions. "
            f"No extra turns, no mass land denial. "
            f"Prioritize fun, interactive gameplay over efficiency."
            if bracket <= 2 else
            f"IMPORTANT: This deck targets bracket 3 (Upgraded). "
            f"Up to 3 game changers allowed. One late-game two-card combo OK (mana value 6+). "
            f"No chaining extra turns, no mass land denial. "
            f"Prioritize strong synergy and high card quality."
            if bracket == 3 else ""
        )

    target_nonland = commander_others - lands
    if total_candidates < target_nonland:
        console.print(
            f"\n[yellow]Warning: Only {total_candidates} eligible cards found "
            f"(need {target_nonland} nonland + {lands} lands).[/yellow]"
        )
        if total_candidates < 30:
            console.print(
                f"[red]Not enough cards in {'/'.join(wubrg_sort(commander.color_identity)) or 'colorless'} "
                f"to build a viable deck. Try a commander with more color overlap.[/red]"
            )
            raise typer.Exit(1)
        console.print("[yellow]Building best possible deck — will be underpowered.[/yellow]\n")

    extra_instructions = bracket_info
    if budget is not None:
        budget_note = (
            f"BUDGET: Keep the total deck price at or under ${budget:.2f} USD. "
            f"Prefer cheaper cards (prices shown in parentheses) when synergy is similar. "
            f"Lands are added separately, so leave some headroom."
        )
        extra_instructions = f"{extra_instructions} {budget_note}".strip()

    if no_llm:
        console.print("[dim]Using heuristic selection (--no-llm)[/dim]")
        picked = heuristic_pick(
            candidates, lands, rng=rng, variety=effective_variety,
            others=commander_others, quotas=quotas,
        )
        deck_picks = []
        for slot, scored_list in picked.items():
            for sc in scored_list:
                deck_picks.append(DeckPick(card=sc.card, slot=sc.slot, reason=", ".join(sc.reasons)))
        strategy = ""
        upgrades = []
    else:
        prior_decks = _load_prior_decks(commander.name) if effective_variety > 0 else None
        if prior_decks:
            console.print(
                f"[dim]Found {len(prior_decks)} prior deck(s) — asking Claude to differ[/dim]"
            )
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            progress.add_task("Asking Claude for deck picks...", total=None)
            try:
                deck_picks, strategy, upgrades = llm_build(
                    commander, candidates, lands,
                    extra_instructions=extra_instructions, owned_names=owned_names,
                    rng=rng, variety=effective_variety, prior_decks=prior_decks,
                    partner=partner, quotas=quotas,
                )
            except Exception as e:
                console.print(f"[yellow]LLM failed ({e}), falling back to heuristic[/yellow]")
                picked = heuristic_pick(
                    candidates, lands, rng=rng, variety=effective_variety,
                    others=commander_others, quotas=quotas,
                )
                deck_picks = []
                for slot, scored_list in picked.items():
                    for sc in scored_list:
                        deck_picks.append(
                            DeckPick(card=sc.card, slot=sc.slot, reason=", ".join(sc.reasons))
                        )
                strategy = ""
                upgrades = []

    # Backfill if LLM returned fewer than needed
    target_nonland = commander_others - lands
    if len(deck_picks) < target_nonland:
        deficit = target_nonland - len(deck_picks)
        picked_names = {p.card.name for p in deck_picks}
        fallback = heuristic_pick(
            candidates, lands, rng=rng, variety=effective_variety,
            others=commander_others, quotas=quotas,
        )
        backfill: list[DeckPick] = []
        for slot, scored_list in fallback.items():
            for sc in scored_list:
                if sc.card.name not in picked_names:
                    backfill.append(DeckPick(card=sc.card, slot=sc.slot, reason="backfill"))
                    picked_names.add(sc.card.name)
        backfill.sort(key=lambda p: p.card.edhrec_rank or 99999)
        deck_picks.extend(backfill[:deficit])
        actually_filled = min(deficit, len(backfill))
        if actually_filled > 0:
            console.print(f"[dim]Backfilled {actually_filled} cards[/dim]")
        if len(deck_picks) < target_nonland:
            shortfall = target_nonland - len(deck_picks)
            console.print(
                f"\n[yellow]Warning: Collection short by {shortfall} cards. "
                f"Deck will have {len(deck_picks) + num_commanders + lands} cards instead of 100.[/yellow]"
            )
            console.print(
                f"[yellow]Adding {shortfall} extra lands to fill. "
                f"Consider acquiring more cards in "
                f"{'/'.join(wubrg_sort(commander.color_identity)) or 'colorless'}.[/yellow]\n"
            )
            lands += shortfall

    # Refinement: if LLM suggested upgrades that we actually own, swap them in
    # Only replace backfill cards or cards with strictly worse EDHREC rank
    if upgrades:
        picked_names = {p.card.name.lower() for p in deck_picks}
        all_candidate_by_name: dict[str, ScoredCard] = {}
        for slot_list in candidates.values():
            for sc in slot_list:
                all_candidate_by_name[sc.card.name.lower()] = sc

        swapped = 0
        for upgrade_name in upgrades[:]:
            sc = all_candidate_by_name.get(upgrade_name.lower())
            if not sc or upgrade_name.lower() in picked_names:
                continue

            upgrade_rank = sc.card.edhrec_rank or 99999

            # Prefer replacing backfill cards first
            same_slot_picks = [
                (i, p) for i, p in enumerate(deck_picks) if p.slot == sc.slot
            ]
            backfill_picks = [(i, p) for i, p in same_slot_picks if "backfill" in p.reason]

            if backfill_picks:
                target_idx, target = backfill_picks[0]
            elif same_slot_picks:
                # Only replace if upgrade is strictly better (lower EDHREC rank)
                target_idx, target = max(
                    same_slot_picks, key=lambda x: x[1].card.edhrec_rank or 99999
                )
                target_rank = target.card.edhrec_rank or 99999
                if upgrade_rank >= target_rank:
                    continue
            else:
                continue

            deck_picks[target_idx] = DeckPick(
                card=sc.card, slot=sc.slot, reason=f"upgrade swap (replaced {target.card.name})"
            )
            picked_names.add(upgrade_name.lower())
            upgrades.remove(upgrade_name)
            swapped += 1

        if swapped:
            console.print(f"[green]Swapped in {swapped} owned upgrade cards[/green]")

    # Filter owned cards from remaining upgrade suggestions
    upgrades = [u for u in upgrades if u.lower() not in owned_names_lower]

    land_cards = [c for c in collection_cards if classify_card(c) == DeckSlot.LAND]
    if bracket_result and bracket_result.excluded_cards:
        excluded_set = {name for name, _ in bracket_result.excluded_cards}
        land_cards = [c for c in land_cards if c.name not in excluded_set]
    land_picks = build_mana_base(
        [p.card for p in deck_picks], land_cards, commander, lands,
        rng=rng, variety=effective_variety, partner=partner,
    )

    all_picks = deck_picks + land_picks

    if budget is not None:
        all_picks, swaps, final_price = enforce_budget(
            all_picks, candidates, commander, budget, partner=partner
        )
        if swaps:
            console.print(f"[green]Budget: swapped {swaps} cards to fit ${budget:.2f}[/green]")
        if final_price > budget:
            console.print(
                f"[yellow]Budget: could not reach ${budget:.2f} — best is "
                f"${final_price:.2f} with the available pool. Add cheaper cards "
                f"to your collection or raise --budget.[/yellow]"
            )
        else:
            console.print(f"[green]Budget: deck fits at ${final_price:.2f} / ${budget:.2f}[/green]")

    deck = Deck(
        commander=commander,
        partner=partner,
        cards=all_picks,
        strategy_summary=strategy,
        upgrade_suggestions=upgrades,
    )

    errors = validate_deck(commander, all_picks, partner=partner)
    if errors:
        console.print("[yellow]Validation warnings:[/yellow]")
        for err in errors:
            console.print(f"  [yellow]![/yellow] {err}")
        console.print()

    if not output:
        DECKS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = _safe_deck_name(commander.name)
        ext = "txt"
        output = DECKS_DIR / f"{safe_name}.{ext}"
        # Avoid overwriting — append number
        counter = 1
        while output.exists():
            counter += 1
            output = DECKS_DIR / f"{safe_name}_{counter}.{ext}"

    exported = export_deck(deck, format) if format != "text" else format_deck(deck, verbose)
    output.write_text(exported)
    console.print(f"\n[green]Deck saved → {output}[/green]")
    console.print(format_deck(deck, verbose=verbose))


@app.command("suggest-commanders")
def suggest_commanders(
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c", help="Path to collection file"
    ),
    colors: Optional[str] = typer.Option(
        None, "--colors", help="Filter by colors: WUBRG letters or a name (esper, jund, azorius)"
    ),
    theme: Optional[str] = typer.Option(
        None, "--theme", help="Rank commanders by fit for an archetype (e.g. aristocrats, dragons)"
    ),
    top: int = typer.Option(5, "--top", help="Number of suggestions"),
    variety: float = typer.Option(
        0.0, "--variety", min=0.0, max=1.0,
        help="Surface different commanders each run (0=deterministic top picks)",
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Random seed for reproducible variety (implies --variety if unset)"
    ),
):
    """Suggest commanders from your collection."""
    theme = _resolve_theme_or_exit(theme)
    color_filter = _resolve_colors_or_exit(colors)
    effective_variety, rng = _setup_variety(variety, seed)
    _require_collection(collection)
    index = _load_index()

    entries = parse_collection(collection)
    match_result = match_collection(entries, index)
    collection_cards = get_unique_cards(match_result.matched)

    owned_commanders = [
        c for c in collection_cards if is_legal_commander(c)
    ]

    if color_filter is not None:
        owned_commanders = [
            c for c in owned_commanders
            if set(c.color_identity).issubset(color_filter)
        ]

    on_theme = (
        {c.name for c in collection_cards if theme_hits(theme, c.oracle_text, c.type_line) > 0}
        if theme else None
    )

    scored_commanders: list[tuple[str, int, int, float]] = []
    for cmdr in owned_commanders:
        identity = set(cmdr.color_identity)
        support = sum(
            1 for c in collection_cards
            if c.name != cmdr.name
            and set(c.color_identity).issubset(identity)
            and (on_theme is None or c.name in on_theme)
        )
        rank = cmdr.edhrec_rank or 99999
        fit = theme_hits(theme, cmdr.oracle_text, cmdr.type_line) if theme else 0
        weight_score = fit * 60 + support + max(0.0, 100 - rank / 300)
        scored_commanders.append((cmdr.name, support, rank, weight_score))

    scored_commanders.sort(key=lambda x: (-x[3], x[2]))

    if effective_variety > 0 and rng is not None and len(scored_commanders) > top:
        pool = scored_commanders[: max(top * 4, top)]
        weights = softmax_weights([x[3] for x in pool], effective_variety)
        chosen = weighted_sample_without_replacement(rng, pool, weights, top)
        chosen.sort(key=lambda x: (-x[1], x[2]))
    else:
        chosen = scored_commanders[:top]

    console.print(f"\n[bold]Top {top} Commander Suggestions:[/bold]\n")
    for i, (name, support, rank, _) in enumerate(chosen, 1):
        card = index.get(name)
        identity = format_colors(card.color_identity) if card else "?"
        console.print(
            f"  {i}. [bold]{name}[/bold] [{identity}] "
            f"— {support} supporting cards (EDHREC #{rank})"
        )


@app.command("update-data")
def update_data(
    force: bool = typer.Option(False, "--force", help="Force re-download"),
):
    """Download/update Scryfall card database."""
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("Downloading Scryfall oracle cards...", total=None)
        path = download_bulk_data(force=force)
    console.print(f"[green]Card database updated: {path}[/green]")


@app.command()
def validate(
    deck_file: Path = typer.Option(..., "--deck", "-d", help="Deck file to validate"),
    commander_name: str = typer.Option(..., "--commander", "-C", help="Commander name"),
):
    """Validate a deck for Commander legality."""
    index = _load_index()

    entries = parse_collection(deck_file)
    match_result = match_collection(entries, index)

    commander = index.get(commander_name)
    if not commander:
        console.print(f"[red]Commander '{commander_name}' not found[/red]")
        raise typer.Exit(1)

    picks = [
        DeckPick(card=e.card, slot=classify_card(e.card))
        for e in match_result.matched
        if e.card and e.card.name != commander.name
    ]

    errors = validate_deck(commander, picks)
    if errors:
        console.print("[red]Deck validation failed:[/red]")
        for err in errors:
            console.print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]Deck is valid! ({len(picks) + 1} cards)[/green]")


@app.command()
def convert(
    input_file: Path = typer.Option(..., "--input", "-i", help="Input collection file (CSV/text)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
):
    """Convert Archidekt/CSV collection export to simple text format."""
    entries = parse_collection(input_file)
    if not entries:
        console.print("[red]No cards found in input file[/red]")
        raise typer.Exit(1)

    aggregated = aggregate_entries(entries)
    text = convert_to_text(entries)
    unique_cards = len(aggregated)
    total_cards = sum(e.quantity for e in aggregated)

    if output:
        output.write_text(text)
        console.print(
            f"[green]Converted {total_cards} cards ({unique_cards} unique) → {output}[/green]"
        )
    else:
        console.print(text)
        console.print(
            f"\n[dim]--- {total_cards} cards total, {unique_cards} unique ---[/dim]"
        )


@app.command()
def suggest(
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c", help="Path to collection file"
    ),
    commander_name: str = typer.Option(..., "--commander", "-C", help="Commander card name"),
    deck_file: Optional[Path] = typer.Option(None, "--deck", "-d", help="Current deck file (for targeted suggestions)"),
    top: int = typer.Option(15, "--top", help="Number of suggestions"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM, use heuristic only"),
    variety: float = typer.Option(
        0.0, "--variety", min=0.0, max=1.0,
        help="Vary suggestions each run (0=deterministic top picks)",
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Random seed for reproducible variety (implies --variety if unset)"
    ),
    theme: Optional[str] = typer.Option(
        None, "--theme", help="Bias suggestions toward an archetype (e.g. aristocrats, tokens)"
    ),
):
    """Suggest cards to BUY that synergize with your commander."""
    from commanderai.deckbuilder.suggester import find_suggestions_heuristic, find_suggestions_llm

    theme = _resolve_theme_or_exit(theme)
    effective_variety, rng = _setup_variety(variety, seed)
    _require_collection(collection)
    index = _load_index()

    entries = parse_collection(collection)
    match_result = match_collection(entries, index)
    owned_names = {e.card.name for e in match_result.matched if e.card}

    commander = index.get(commander_name)
    if not commander:
        console.print(f"[red]Commander '{commander_name}' not found[/red]")
        raise typer.Exit(1)

    deck_cards = []
    if deck_file:
        deck_entries = parse_collection(deck_file)
        deck_match = match_collection(deck_entries, index)
        deck_cards = [e.card for e in deck_match.matched if e.card and e.card.name != commander.name]

    console.print(f"[bold]Suggesting upgrades for:[/bold] {commander.name}")
    console.print(f"[dim]Collection: {len(owned_names)} unique cards owned[/dim]\n")

    if no_llm:
        suggestions = find_suggestions_heuristic(
            commander, index.all_cards, owned_names, top_n=top,
            rng=rng, variety=effective_variety, theme=theme,
        )
        if not suggestions:
            console.print("[yellow]No synergy suggestions found.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[bold]Top {len(suggestions)} cards to buy:[/bold]\n")
        for i, (card, themes) in enumerate(suggestions, 1):
            price = card.prices.get("usd") or "?"
            rank = card.edhrec_rank or "?"
            console.print(
                f"  {i:2}. [bold]{card.name}[/bold]  {card.mana_cost}  "
                f"[dim](${price}, EDHREC #{rank})[/dim]"
            )
            console.print(f"      [dim]{card.oracle_text[:120]}[/dim]")
            console.print(f"      [green]Synergy: {', '.join(themes)}[/green]")
            console.print()
    else:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            progress.add_task("Asking Claude for upgrade suggestions...", total=None)
            try:
                result = find_suggestions_llm(
                    commander, deck_cards or [], owned_names, index.all_cards, top_n=top,
                    rng=rng, variety=effective_variety, theme=theme,
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1)

        console.print(result)


@app.command()
def explain(
    deck_file: Path = typer.Option(..., "--deck", "-d", help="Deck file to explain"),
    commander_name: Optional[str] = typer.Option(
        None, "--commander", "-C", help="Commander name (auto-detected from Archidekt format)"
    ),
):
    """Explain a deck's strategy, synergies, and win conditions using AI."""
    from commanderai.deckbuilder.explainer import explain_deck

    index = _load_index()

    entries = parse_collection(deck_file)
    if not entries:
        console.print("[red]No cards found in deck file[/red]")
        raise typer.Exit(1)

    match_result = match_collection(entries, index)
    matched_cards = [e.card for e in match_result.matched if e.card]

    commander = None
    if commander_name:
        commander = index.get(commander_name)
    else:
        for entry in match_result.matched:
            if entry.card and is_legal_commander(entry.card):
                commander = entry.card
                break

    if not commander:
        console.print("[red]Could not identify commander. Use --commander flag.[/red]")
        raise typer.Exit(1)

    deck_cards = [c for c in matched_cards if c.name != commander.name]
    console.print(f"[bold]Explaining:[/bold] {commander.name} ({len(deck_cards)} cards)\n")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("Analyzing deck with Claude...", total=None)
        try:
            explanation = explain_deck(commander, deck_cards)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

    console.print(explanation)


@app.command()
def tokens(
    deck_file: Path = typer.Option(..., "--deck", "-d", help="Deck file to analyze"),
):
    """List all tokens that cards in a deck can create."""
    from commanderai.deckbuilder.tokens import extract_tokens

    index = _load_index()

    entries = parse_collection(deck_file)
    if not entries:
        console.print("[red]No cards found in deck file[/red]")
        raise typer.Exit(1)

    match_result = match_collection(entries, index)
    matched_cards = [e.card for e in match_result.matched if e.card]

    token_list = extract_tokens(matched_cards)

    if not token_list:
        console.print("[yellow]No token-creating cards found in this deck.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Tokens needed ({len(token_list)} unique):[/bold]\n")
    for t in token_list:
        parts = []
        if t.power and t.toughness:
            parts.append(f"{t.power}/{t.toughness}")
        if t.colors:
            parts.append(" ".join(t.colors))
        if t.types:
            parts.append(t.types)
        parts.append(f"— {t.name}")
        if t.keywords:
            parts.append(f"({', '.join(t.keywords)})")

        header = " ".join(parts)
        creators = ", ".join(t.created_by)
        console.print(f"  [green]•[/green] {header}")
        console.print(f"    [dim]Created by: {creators}[/dim]")

    console.print(f"\n[dim]Total: {len(token_list)} unique tokens from {len(matched_cards)} cards[/dim]")


def _head_tail(items: "list", head: Optional[int], tail: Optional[int]) -> tuple["list", str]:
    """Slice a list for --head/--tail and return (subset, note)."""
    total = len(items)
    if head is not None and head < total:
        return items[:head], f" (showing first {head} of {total})"
    if tail is not None and tail < total:
        return items[-tail:], f" (showing last {tail} of {total})"
    return items, ""


class ListCategory(str, Enum):
    commanders = "commanders"
    decks = "decks"
    colors = "colors"
    themes = "themes"
    tribes = "tribes"
    aliases = "aliases"
    formats = "formats"
    brackets = "brackets"


_EXPORT_FORMATS = {
    "text": "Plain '1 Card' list (default)",
    "mtgo": "MTGO-compatible list",
    "moxfield": "Moxfield import (commanders tagged *CMDR*)",
    "archidekt": "Archidekt import (cards tagged by slot)",
}

_BRACKET_DESCRIPTIONS = {
    1: "Exhibition — no game changers, combos, extra turns, or MLD",
    2: "Core — no game changers, no two-card combos, no extra turns/MLD",
    3: "Upgraded — up to 3 game changers, 1 late combo (≥6 mana)",
    4: "Optimized — no restrictions (banlist only)",
    5: "cEDH — full power, no filtering applied",
}

# Group the color names for readable output.
_COLOR_GROUPS = [
    ("Mono", ["white", "blue", "black", "red", "green"]),
    ("Guilds (2)", ["azorius", "dimir", "rakdos", "gruul", "selesnya",
                    "orzhov", "izzet", "golgari", "boros", "simic"]),
    ("Shards & Wedges (3)", ["esper", "grixis", "jund", "naya", "bant",
                             "jeskai", "sultai", "mardu", "temur", "abzan"]),
    ("Four-color", ["yore-tiller", "glint-eye", "dune-brood", "ink-treader", "witch-maw"]),
    ("Five-color", ["five-color"]),
]


def _deck_summary(path: Path) -> tuple[str, int]:
    """Return (commander label, card count) for a saved deck file."""
    commander = ""
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.match(r"^=== Commanders?:\s*(.+?)\s*===$", line)
        if m:
            commander = m.group(1)
            continue
        if re.match(r"^\d+x?\s+\S", line):
            count += 1
            if not commander:
                name = re.sub(r"^\d+x?\s+", "", line)
                name = re.split(r"\s+(?:\[|\*|\{)", name, maxsplit=1)[0].strip()
                commander = name
    return commander, count


@app.command("list")
def list_(
    category: ListCategory = typer.Argument(
        ...,
        help="What to list: commanders, decks, colors, themes, tribes, aliases, formats, brackets",
    ),
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c",
        help="Collection file (used by `list commanders`)",
    ),
    colors: Optional[str] = typer.Option(
        None, "--colors", help="Filter `list commanders` by colors (e.g. jund, WUB)"
    ),
    head: Optional[int] = typer.Option(None, "--head", min=1, help="Show only the first N entries"),
    tail: Optional[int] = typer.Option(None, "--tail", min=1, help="Show only the last N entries"),
):
    """List eligible commanders, saved decks, or the vocabularies used by the flags."""
    if head is not None and tail is not None:
        console.print("[red]Use either --head or --tail, not both.[/red]")
        raise typer.Exit(1)

    if category == ListCategory.commanders:
        color_filter = _resolve_colors_or_exit(colors)
        _require_collection(collection)
        index = _load_index()
        match_result = match_collection(parse_collection(collection), index)
        collection_cards = get_unique_cards(match_result.matched)

        commanders = [c for c in collection_cards if is_legal_commander(c)]
        if color_filter is not None:
            commanders = [c for c in commanders if set(c.color_identity).issubset(color_filter)]
        commanders.sort(key=lambda c: (c.edhrec_rank or 99999, c.name))

        if not commanders:
            console.print("[yellow]No eligible commanders found in your collection.[/yellow]")
            return
        total = len(commanders)
        commanders, note = _head_tail(commanders, head, tail)
        console.print(f"\n[bold]Eligible commanders ({total}):[/bold]{note}\n")
        for c in commanders:
            identity = format_colors(c.color_identity)
            rank = c.edhrec_rank or "?"
            ability = partner_ability(c)
            tags = []
            if ability.partner_with:
                tags.append(f"Partner with {ability.partner_with[0]}")
            elif ability.plain:
                tags.append("Partner")
            if ability.group:
                tags.append(f"Partner — {ability.group}")
            if ability.background_chooser:
                tags.append("Choose a Background")
            if ability.doctors_companion:
                tags.append("Doctor's companion")
            if ability.friends_forever:
                tags.append("Friends forever")
            tag_str = f"  [magenta]({', '.join(tags)})[/magenta]" if tags else ""
            console.print(
                f"  [bold]{c.name}[/bold] [{identity}] [dim]EDHREC #{rank}[/dim]{tag_str}"
            )
        return

    if category == ListCategory.decks:
        if not DECKS_DIR.exists():
            console.print("[yellow]No decks directory yet. Build a deck first.[/yellow]")
            return
        files = sorted(
            DECKS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not files:
            console.print("[yellow]No saved decks in decks/ yet.[/yellow]")
            return
        total = len(files)
        files, note = _head_tail(files, head, tail)
        console.print(f"\n[bold]Saved decks ({total}):[/bold]{note}\n")
        for path in files:
            commander, count = _deck_summary(path)
            label = f" — [dim]{commander}[/dim]" if commander else ""
            console.print(f"  [green]{path.name}[/green] ({count} cards){label}")

    elif category == ListCategory.colors:
        console.print("\n[bold]Color combinations[/bold] (use with --colors):\n")
        for group, names in _COLOR_GROUPS:
            console.print(f"  [bold]{group}[/bold]")
            for name in names:
                console.print(f"    {name:14} [dim]{COLOR_NAMES.get(name, '')}[/dim]")
            console.print()

    elif category == ListCategory.themes:
        names = archetype_names()
        console.print(f"\n[bold]Archetypes ({len(names)})[/bold] (use with --theme):\n")
        for name in names:
            console.print(f"  {name}")
        console.print("\n[dim]Also accepts tribes (`list tribes`) and aliases (`list aliases`).[/dim]")

    elif category == ListCategory.tribes:
        tribes = sorted(TRIBES)
        console.print(f"\n[bold]Creature tribes ({len(tribes)})[/bold] (use with --theme):\n")
        cols = 4
        for i in range(0, len(tribes), cols):
            console.print("  " + "".join(f"{t:16}" for t in tribes[i:i + cols]))

    elif category == ListCategory.aliases:
        console.print(f"\n[bold]Theme aliases ({len(ALIASES)})[/bold] → canonical:\n")
        for alias in sorted(ALIASES):
            console.print(f"  {alias:18} [dim]→ {ALIASES[alias]}[/dim]")

    elif category == ListCategory.formats:
        console.print("\n[bold]Export formats[/bold] (use with -f/--format):\n")
        for name, desc in _EXPORT_FORMATS.items():
            console.print(f"  [green]{name:10}[/green] [dim]{desc}[/dim]")

    elif category == ListCategory.brackets:
        console.print("\n[bold]Power brackets[/bold] (use with -b/--bracket):\n")
        for level, desc in _BRACKET_DESCRIPTIONS.items():
            console.print(f"  [green]{level}[/green]  [dim]{desc}[/dim]")


if __name__ == "__main__":
    app()
