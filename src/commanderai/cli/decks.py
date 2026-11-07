"""`commanderai decks ...` — the deck library (SQLite) from the command line."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from commanderai.cli.render import ConsoleReporter, render_error
from commanderai.config import DEFAULT_COLLECTION
from commanderai.errors import CommanderAIError
from commanderai.output.formatter import format_deck
from commanderai.services.context import ServiceContext
from commanderai.services.library import (
    EXPORT_FORMATS,
    delete_deck,
    export_deck,
    get_deck,
    import_deck,
    list_decks,
    migrate_legacy_decks,
    rename_deck,
)
from commanderai.settings import get_settings
from commanderai.storage import DeckSummary

decks_app = typer.Typer(help="Manage saved decks (the deck database).", no_args_is_help=True)


def _console():
    from commanderai.cli.commands import console

    return console


def _context() -> ServiceContext:
    return ServiceContext(settings=get_settings(), reporter=ConsoleReporter(_console()))


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CommanderAIError as err:
        render_error(_console(), err, default_collection=DEFAULT_COLLECTION)
        raise typer.Exit(1)


def display_path(path: str | None) -> str:
    """Path relative to the current directory when possible."""
    if not path:
        return ""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def display_time(iso: str | None) -> str:
    return (iso or "")[:16].replace("T", " ")


def deck_lines(d: DeckSummary) -> list[str]:
    """Two lines per deck: identity, then provenance."""
    name = f"[bold]{d.name}[/bold]"
    if d.name != d.commander_label:
        name += f" ({d.commander_label})"
    meta = [d.source, display_time(d.created_at)]
    if d.export_path:
        meta.append(display_path(d.export_path))
    return [
        f"  [green]#{d.id}[/green]  {name} [{d.colors}] — {d.card_count} cards, ${d.total_price:.2f}",
        f"      [dim]{' · '.join(meta)}[/dim]",
    ]


def print_deck_list(commander: str | None, head: int | None, tail: int | None) -> None:
    from commanderai.cli.commands import _head_tail

    console = _console()
    decks = _run(list_decks, _context(), commander=commander)
    if not decks:
        console.print("[yellow]No saved decks yet. Build a deck first.[/yellow]")
        return
    total = len(decks)
    decks, note = _head_tail(decks, head, tail)
    console.print(f"\n[bold]Saved decks ({total}):[/bold]{note}\n")
    for d in decks:
        for line in deck_lines(d):
            console.print(line)


@decks_app.command("list")
def list_cmd(
    commander: str | None = typer.Option(None, "--commander", "-C", help="Only decks for this commander"),
    head: int | None = typer.Option(None, "--head", min=1, help="Show only the newest N decks"),
    tail: int | None = typer.Option(None, "--tail", min=1, help="Show only the oldest N decks"),
):
    """List saved decks, newest first."""
    if head is not None and tail is not None:
        _console().print("[red]Use either --head or --tail, not both.[/red]")
        raise typer.Exit(1)
    print_deck_list(commander, head, tail)


@decks_app.command("show")
def show_cmd(
    deck_id: int = typer.Argument(..., help="Deck id (see `decks list`)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show why each card was picked"),
):
    """Show a saved deck with its build details."""
    console = _console()
    rec = _run(get_deck, _context(), deck_id)
    console.print(f"\n[bold]Deck #{rec.id} — {rec.name}[/bold]")
    info = [f"source {rec.source}", f"created {display_time(rec.created_at)}"]
    if rec.export_path:
        info.append(f"file {display_path(rec.export_path)}")
    console.print(f"[dim]{' · '.join(info)}[/dim]")
    build = rec.build or {}
    request = build.get("request") or {}
    params = []
    if build.get("theme"):
        params.append(f"theme {build['theme']}")
    if build.get("color_filter"):
        params.append(f"colors {''.join(build['color_filter'])}")
    if build.get("seed") is not None:
        params.append(f"seed {build['seed']} (variety {build.get('variety', 0):.2f})")
    if request.get("bracket"):
        params.append(f"bracket {request['bracket']}")
    if request.get("budget") is not None:
        params.append(f"budget ${request['budget']:.2f}")
    if build:
        params.append(f"lands {build.get('lands')}")
    if params:
        console.print(f"[dim]Build: {' · '.join(params)}[/dim]")
    if rec.notes:
        console.print(f"[dim]Notes: {rec.notes}[/dim]")
    console.print()
    console.print(format_deck(rec.deck, verbose=verbose))


@decks_app.command("export")
def export_cmd(
    deck_id: int = typer.Argument(..., help="Deck id"),
    format: str = typer.Option("json", "--format", "-f", help=f"One of: {', '.join(EXPORT_FORMATS)}"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to a file instead of stdout"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Include pick reasons (text format)"),
):
    """Export a saved deck as JSON (re-importable) or a text decklist format."""
    rec = _run(get_deck, _context(), deck_id)
    text = _run(export_deck, rec, format, verbose)
    if output:
        output.write_text(text)
        _console().print(f"[green]Exported deck #{rec.id} ({format}) → {output}[/green]")
    else:
        typer.echo(text, nl=not text.endswith("\n"))


@decks_app.command("import")
def import_cmd(
    file: Path = typer.Argument(..., help="A JSON deck export, or a text decklist"),
    name: str | None = typer.Option(None, "--name", "-n", help="Name for the imported deck"),
):
    """Import a deck (JSON export or text decklist) into the database."""
    console = _console()
    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)
    rec, unknown = _run(import_deck, _context(), file.read_text(encoding="utf-8"),
                        name=name, filename=file.name)
    console.print(f"[green]Imported deck #{rec.id} — {rec.name} ({rec.deck.size} cards)[/green]")
    if unknown:
        console.print(f"[yellow]Skipped {len(unknown)} unknown card(s): {', '.join(unknown)}[/yellow]")


@decks_app.command("rename")
def rename_cmd(
    deck_id: int = typer.Argument(..., help="Deck id"),
    name: str = typer.Argument(..., help="New name"),
):
    """Rename a saved deck."""
    rec = _run(rename_deck, _context(), deck_id, name)
    _console().print(f"[green]Renamed deck #{rec.id} → {rec.name}[/green]")


@decks_app.command("delete")
def delete_cmd(
    deck_id: int = typer.Argument(..., help="Deck id"),
):
    """Delete a saved deck from the database (exported text files are kept)."""
    rec = _run(delete_deck, _context(), deck_id)
    _console().print(f"[green]Deleted deck #{rec.id} — {rec.name}[/green]")


@decks_app.command("migrate")
def migrate_cmd(
    directory: Path | None = typer.Option(
        None, "--dir", help="Directory of legacy .txt decks (default: the decks directory)"
    ),
):
    """Import legacy .txt deck files that are not in the database yet.

    Files that failed to import before are retried.
    """
    ctx = _context()
    report = _run(migrate_legacy_decks, ctx, directory, retry_failed=True)
    if not report.imported and not report.failed:
        _console().print(
            f"[dim]No new deck files to import ({report.scanned} scanned, "
            f"{report.already_known} already known).[/dim]"
        )
