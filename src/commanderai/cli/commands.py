"""Typer command definitions. Each command: parse options → call a service →
render the result. All logic lives in :mod:`commanderai.services`."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import TypeVar

import typer
from pydantic import ValidationError
from rich.console import Console

from commanderai.cli.decks import decks_app, print_deck_list
from commanderai.cli.render import ConsoleReporter, render_error, spinner
from commanderai.config import DEFAULT_COLLECTION, DEFAULT_LAND_COUNT
from commanderai.data.scryfall import download_bulk_data
from commanderai.deckbuilder.colors import COLOR_NAMES
from commanderai.errors import CommanderAIError
from commanderai.output.formatter import format_deck
from commanderai.services.analysis import deck_tokens, explain_deck_list, validate_deck_list
from commanderai.services.build import BuildRequest, build_deck
from commanderai.services.collection import convert_collection
from commanderai.services.commanders import list_commanders
from commanderai.services.commanders import suggest_commanders as suggest_commanders_service
from commanderai.services.context import ServiceContext
from commanderai.services.deck_files import next_deck_path, write_deck_file
from commanderai.services.library import mark_exported, save_build
from commanderai.services.reference import (
    BRACKET_DESCRIPTIONS,
    COLOR_GROUPS,
    EXPORT_FORMATS,
    aliases,
    archetypes,
    tribes,
)
from commanderai.services.suggest import UpgradeRequest, suggest_upgrades
from commanderai.settings import get_settings

app = typer.Typer(name="commanderai", help="AI-powered Commander deck builder")
console = Console()
app.add_typer(decks_app, name="decks")

T = TypeVar("T")


def _context() -> ServiceContext:
    return ServiceContext(settings=get_settings(), reporter=ConsoleReporter(console))


def _run(fn: Callable[..., T], *args, **kwargs) -> T:
    """Call a service; render domain/validation errors and exit 1 on failure."""
    try:
        return fn(*args, **kwargs)
    except CommanderAIError as err:
        render_error(console, err, default_collection=DEFAULT_COLLECTION)
        raise typer.Exit(1)
    except ValidationError as err:
        for e in err.errors():
            loc = ".".join(str(p) for p in e["loc"])
            console.print(f"[red]Invalid value for {loc}: {e['msg']}[/red]")
        raise typer.Exit(1)


@app.command()
def build(
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c", help="Path to collection file"
    ),
    commander_name: str | None = typer.Option(
        None, "--commander", "-C",
        help="Commander card name (omit to auto-pick from --theme/--colors)",
    ),
    partner_name: str | None = typer.Option(
        None, "--partner", "-P",
        help="Second commander (Partner / Background / Doctor's companion etc.)",
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM, use heuristic only"),
    lands: int = typer.Option(DEFAULT_LAND_COUNT, "--lands", help="Number of lands"),
    variety: float = typer.Option(
        0.0, "--variety", min=0.0, max=1.0,
        help="Deck variety 0.0-1.0 (0=deterministic; higher = more variation between builds)",
    ),
    seed: int | None = typer.Option(
        None, "--seed", help="Random seed for reproducible variety (implies --variety if unset)"
    ),
    theme: str | None = typer.Option(
        None, "--theme", help="Archetype to lean into (e.g. aristocrats, tokens, dragons)"
    ),
    colors: str | None = typer.Option(
        None, "--colors",
        help="Color filter for auto-pick: WUBRG letters or a name (esper, jund, azorius)",
    ),
    budget: float | None = typer.Option(None, "--budget", help="Max deck price in USD"),
    bracket: int | None = typer.Option(None, "--bracket", "-b", min=1, max=5, help="Power bracket 1-5 (1=casual, 5=cEDH)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write deck to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show scoring details"),
    format: str = typer.Option("text", "--format", "-f", help="Output format"),
):
    """Build a Commander deck from your collection.

    Provide --commander, or omit it and pass --theme and/or --colors to
    auto-pick the best-fit commander you own.
    """
    if format not in EXPORT_FORMATS:
        console.print(
            f"[red]Unknown format '{format}'. Options: {', '.join(EXPORT_FORMATS)}[/red]"
        )
        raise typer.Exit(1)
    ctx = _context()
    request = _run(
        BuildRequest,
        collection=collection, commander=commander_name, partner=partner_name,
        theme=theme, colors=colors, lands=lands, variety=variety, seed=seed,
        budget=budget, bracket=bracket, use_llm=not no_llm, verbose=verbose,
    )
    result = _run(build_deck, ctx, request)
    deck = result.deck

    if not output:
        output = next_deck_path(ctx.settings.decks_dir, deck.commander.name)
    # The database is the source of truth; the text file is an export of it.
    record = _run(save_build, ctx, result, source="cli", export_path=output, export_format=format)
    write_deck_file(deck, output, format, verbose)
    mark_exported(ctx, record, output)
    console.print(f"\n[green]Deck saved → {output}[/green] [dim](deck #{record.id})[/dim]")
    console.print(format_deck(deck, verbose=verbose))


@app.command("suggest-commanders")
def suggest_commanders(
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c", help="Path to collection file"
    ),
    colors: str | None = typer.Option(
        None, "--colors", help="Filter by colors: WUBRG letters or a name (esper, jund, azorius)"
    ),
    theme: str | None = typer.Option(
        None, "--theme", help="Rank commanders by fit for an archetype (e.g. aristocrats, dragons)"
    ),
    top: int = typer.Option(5, "--top", help="Number of suggestions"),
    variety: float = typer.Option(
        0.0, "--variety", min=0.0, max=1.0,
        help="Surface different commanders each run (0=deterministic top picks)",
    ),
    seed: int | None = typer.Option(
        None, "--seed", help="Random seed for reproducible variety (implies --variety if unset)"
    ),
):
    """Suggest commanders from your collection."""
    result = _run(
        suggest_commanders_service, _context(), collection,
        colors=colors, theme=theme, top=top, variety=variety, seed=seed,
    )
    console.print(f"\n[bold]Top {top} Commander Suggestions:[/bold]\n")
    for i, s in enumerate(result.suggestions, 1):
        console.print(
            f"  {i}. [bold]{s.commander.name}[/bold] [{s.commander.colors}] "
            f"— {s.support} supporting cards (EDHREC #{s.edhrec_rank})"
        )


@app.command("update-data")
def update_data(
    force: bool = typer.Option(False, "--force", help="Force re-download"),
):
    """Download/update Scryfall card database."""
    settings = get_settings()
    if settings.offline:
        console.print("[red]Offline mode (COMMANDERAI_OFFLINE=1): not downloading.[/red]")
        raise typer.Exit(1)
    with spinner(console, "Downloading Scryfall oracle cards..."):
        path = download_bulk_data(force=force, dest=settings.oracle_cards_path)
    console.print(f"[green]Card database updated: {path}[/green]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to listen on"),
    port: int = typer.Option(8000, "--port", "-p", help="Port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (development)"),
):
    """Start the web UI and HTTP API (http://127.0.0.1:8000)."""
    from importlib.util import find_spec

    if find_spec("fastapi") is None or find_spec("uvicorn") is None:
        console.print("[red]The web UI needs the 'web' extra: pip install -e '.[web]'[/red]")
        raise typer.Exit(1)
    import uvicorn

    console.print(f"[green]CommanderAI UI → http://{host}:{port}[/green]  [dim](API docs: /api/docs)[/dim]")
    uvicorn.run("commanderai.api.app:create_app", factory=True, host=host, port=port, reload=reload)


@app.command()
def validate(
    deck_file: Path = typer.Option(..., "--deck", "-d", help="Deck file to validate"),
    commander_name: str = typer.Option(..., "--commander", "-C", help="Commander name"),
    partner_name: str | None = typer.Option(
        None, "--partner", "-P", help="Second commander (Partner / Background / ...)"
    ),
):
    """Validate a deck for Commander legality."""
    result = _run(validate_deck_list, _context(), deck_file, commander_name, partner_name)
    if result.unknown_cards:
        console.print(
            f"[yellow]{len(result.unknown_cards)} card(s) not recognised (not counted): "
            f"{', '.join(result.unknown_cards)}[/yellow]"
        )
    if result.errors:
        console.print("[red]Deck validation failed:[/red]")
        for err in result.errors:
            console.print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    console.print(f"[green]Deck is valid! ({result.card_count} cards)[/green]")


@app.command()
def convert(
    input_file: Path = typer.Option(..., "--input", "-i", help="Input collection file (CSV/text)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
):
    """Convert Archidekt/CSV collection export to simple text format."""
    result = _run(convert_collection, input_file)
    if output:
        output.write_text(result.text)
        console.print(
            f"[green]Converted {result.total_cards} cards ({result.unique_cards} unique) → {output}[/green]"
        )
    else:
        console.print(result.text)
        console.print(
            f"\n[dim]--- {result.total_cards} cards total, {result.unique_cards} unique ---[/dim]"
        )


@app.command()
def suggest(
    collection: Path = typer.Option(
        DEFAULT_COLLECTION, "--collection", "-c", help="Path to collection file"
    ),
    commander_name: str = typer.Option(..., "--commander", "-C", help="Commander card name"),
    deck_file: Path | None = typer.Option(None, "--deck", "-d", help="Current deck file (for targeted suggestions)"),
    top: int = typer.Option(15, "--top", help="Number of suggestions"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM, use heuristic only"),
    variety: float = typer.Option(
        0.0, "--variety", min=0.0, max=1.0,
        help="Vary suggestions each run (0=deterministic top picks)",
    ),
    seed: int | None = typer.Option(
        None, "--seed", help="Random seed for reproducible variety (implies --variety if unset)"
    ),
    theme: str | None = typer.Option(
        None, "--theme", help="Bias suggestions toward an archetype (e.g. aristocrats, tokens)"
    ),
):
    """Suggest cards to BUY that synergize with your commander."""
    request = _run(
        UpgradeRequest,
        collection=collection, commander=commander_name, deck=deck_file, top=top,
        use_llm=not no_llm, variety=variety, seed=seed, theme=theme,
    )
    result = _run(suggest_upgrades, _context(), request)

    if result.llm_text is not None:
        console.print(result.llm_text)
        return

    if not result.suggestions:
        console.print("[yellow]No synergy suggestions found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Top {len(result.suggestions)} cards to buy:[/bold]\n")
    for i, s in enumerate(result.suggestions, 1):
        card = s.card
        price = card.price_label() or "?"
        rank = card.edhrec_rank or "?"
        console.print(
            f"  {i:2}. [bold]{card.name}[/bold]  {card.mana_cost}  "
            f"[dim](${price}, EDHREC #{rank})[/dim]"
        )
        console.print(f"      [dim]{card.oracle_text[:120]}[/dim]")
        console.print(f"      [green]Synergy: {', '.join(s.synergies)}[/green]")
        console.print()


@app.command()
def explain(
    deck_file: Path = typer.Option(..., "--deck", "-d", help="Deck file to explain"),
    commander_name: str | None = typer.Option(
        None, "--commander", "-C", help="Commander name (auto-detected from Archidekt format)"
    ),
):
    """Explain a deck's strategy, synergies, and win conditions using AI."""
    result = _run(explain_deck_list, _context(), deck_file, commander_name)
    console.print(result.explanation)


@app.command()
def tokens(
    deck_file: Path = typer.Option(..., "--deck", "-d", help="Deck file to analyze"),
):
    """List all tokens that cards in a deck can create."""
    result = _run(deck_tokens, _context(), deck_file)

    if not result.tokens:
        console.print("[yellow]No token-creating cards found in this deck.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Tokens needed ({len(result.tokens)} unique):[/bold]\n")
    for t in result.tokens:
        parts = []
        if t.power and t.toughness:
            parts.append(f"{t.power}/{t.toughness}")
        if t.colors:
            parts.append(" ".join(t.colors))
        if t.types:
            parts.append(t.types)
        parts.append(f"— {t.name}" if parts else t.name)
        if t.keywords:
            parts.append(f"({', '.join(t.keywords)})")

        header = " ".join(parts)
        creators = ", ".join(t.created_by)
        console.print(f"  [green]•[/green] {header}")
        console.print(f"    [dim]Created by: {creators}[/dim]")

    console.print(
        f"\n[dim]Total: {len(result.tokens)} unique tokens from {result.card_count} cards[/dim]"
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def _head_tail(items: list, head: int | None, tail: int | None) -> tuple[list, str]:
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
    colors: str | None = typer.Option(
        None, "--colors", help="Filter `list commanders` by colors (e.g. jund, WUB)"
    ),
    head: int | None = typer.Option(None, "--head", min=1, help="Show only the first N entries"),
    tail: int | None = typer.Option(None, "--tail", min=1, help="Show only the last N entries"),
):
    """List eligible commanders, saved decks, or the vocabularies used by the flags."""
    if head is not None and tail is not None:
        console.print("[red]Use either --head or --tail, not both.[/red]")
        raise typer.Exit(1)

    if category == ListCategory.commanders:
        _list_commanders(collection, colors, head, tail)
    elif category == ListCategory.decks:
        _list_decks(head, tail)
    elif category == ListCategory.colors:
        console.print("\n[bold]Color combinations[/bold] (use with --colors):\n")
        for group, names in COLOR_GROUPS:
            console.print(f"  [bold]{group}[/bold]")
            for name in names:
                console.print(f"    {name:14} [dim]{COLOR_NAMES.get(name, '')}[/dim]")
            console.print()
    elif category == ListCategory.themes:
        names = [t.name for t in archetypes()]
        console.print(f"\n[bold]Archetypes ({len(names)})[/bold] (use with --theme):\n")
        for name in names:
            console.print(f"  {name}")
        console.print("\n[dim]Also accepts tribes (`list tribes`) and aliases (`list aliases`).[/dim]")
    elif category == ListCategory.tribes:
        names = [t.name for t in tribes()]
        console.print(f"\n[bold]Creature tribes ({len(names)})[/bold] (use with --theme):\n")
        cols = 4
        for i in range(0, len(names), cols):
            console.print("  " + "".join(f"{t:16}" for t in names[i:i + cols]))
    elif category == ListCategory.aliases:
        items = aliases()
        console.print(f"\n[bold]Theme aliases ({len(items)})[/bold] → canonical:\n")
        for a in items:
            console.print(f"  {a.alias:18} [dim]→ {a.target}[/dim]")
    elif category == ListCategory.formats:
        console.print("\n[bold]Export formats[/bold] (use with -f/--format):\n")
        for name, desc in EXPORT_FORMATS.items():
            console.print(f"  [green]{name:10}[/green] [dim]{desc}[/dim]")
    elif category == ListCategory.brackets:
        console.print("\n[bold]Power brackets[/bold] (use with -b/--bracket):\n")
        for level, desc in BRACKET_DESCRIPTIONS.items():
            console.print(f"  [green]{level}[/green]  [dim]{desc}[/dim]")


def _list_commanders(collection: Path, colors: str | None, head, tail) -> None:
    commanders = _run(list_commanders, _context(), collection, colors)
    if not commanders:
        console.print("[yellow]No eligible commanders found in your collection.[/yellow]")
        return
    total = len(commanders)
    commanders, note = _head_tail(commanders, head, tail)
    console.print(f"\n[bold]Eligible commanders ({total}):[/bold]{note}\n")
    for c in commanders:
        rank = c.edhrec_rank or "?"
        tag_str = f"  [magenta]({', '.join(c.partner_tags)})[/magenta]" if c.partner_tags else ""
        console.print(f"  [bold]{c.name}[/bold] [{c.colors}] [dim]EDHREC #{rank}[/dim]{tag_str}")


def _list_decks(head, tail) -> None:
    print_deck_list(None, head, tail)
