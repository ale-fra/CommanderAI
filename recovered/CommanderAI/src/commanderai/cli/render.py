"""Console presentation for the CLI: notices, progress spinners, and errors.

Services emit structured notices (see :mod:`commanderai.reporting`). This
module turns them back into Rich console output. Codes listed in
``_RENDERERS`` have bespoke formatting (mixed styles, blank lines, item lists);
any other notice is printed in the style of its level.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from commanderai.errors import CollectionNotFoundError, CommanderAIError, LLMError
from commanderai.reporting import Level, Notice, Reporter

_LEVEL_STYLE = {
    Level.INFO: None,
    Level.DETAIL: "dim",
    Level.SUCCESS: "green",
    Level.WARNING: "yellow",
    Level.ERROR: "red",
}


def styled(text: str, style: str | None) -> str:
    return f"[{style}]{text}[/{style}]" if style else text


@contextmanager
def spinner(console: Console, description: str) -> Iterator[None]:
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task(description, total=None)
        yield


# ---------------------------------------------------------------------------
# Bespoke notice renderers
# ---------------------------------------------------------------------------

def _matched(c: Console, n: Notice) -> None:
    d = n.data
    parts = [f"[green]Matched {d['matched']} cards[/green]"]
    if d.get("skipped"):
        parts.append(f"[dim]{d['skipped']} tokens/special skipped[/dim]")
    if d.get("unmatched"):
        parts.append(f"[dim]{d['unmatched']} unmatched[/dim]")
    c.print(" | ".join(parts))


def _fuzzy(c: Console, n: Notice) -> None:
    c.print(f"  [yellow]~[/yellow] '{n.data['original']}' → '{n.data['corrected']}'")


def _unmatched(c: Console, n: Notice) -> None:
    c.print(f"  [red]✗[/red] '{n.data['name']}' not found")


def _auto_commander(c: Console, n: Notice) -> None:
    d = n.data
    c.print(
        f"[green]Auto-selected commander:[/green] {d['name']} "
        f"[{d['colors']}] — {', '.join(d['reasons'])}"
    )


def _auto_partner(c: Console, n: Notice) -> None:
    c.print(f"[green]Auto-selected partner:[/green] {n.data['name']} [{n.data['colors']}]")


def _commander_selected(c: Console, n: Notice) -> None:
    cmdrs = n.data["commanders"]
    if len(cmdrs) > 1:
        c.print(
            f"\n[bold]Commanders:[/bold] {' + '.join(x['name'] for x in cmdrs)} "
            f"[{n.data['colors']}]"
        )
        for x in cmdrs:
            c.print(f"[dim]{x['name']}: {x['oracle_text']}[/dim]")
        c.print()
    else:
        x = cmdrs[0]
        c.print(f"\n[bold]Commander:[/bold] {x['name']} — {x['type_line']}")
        c.print(f"[dim]{x['oracle_text']}[/dim]\n")


def _bracket_excluded_cards(c: Console, n: Notice) -> None:
    cards = n.data["cards"]
    c.print(f"\n[yellow]Bracket {n.data['bracket']} — excluded {len(cards)} cards:[/yellow]")
    for x in cards[:15]:
        c.print(f"  [red]✗[/red] {x['name']} ({x['reason']})")
    if len(cards) > 15:
        c.print(f"  [dim]... and {len(cards) - 15} more[/dim]")


def _bracket_excluded_combos(c: Console, n: Notice) -> None:
    combos = n.data["combos"]
    c.print(f"[yellow]Excluded {len(combos)} combos:[/yellow]")
    for x in combos[:5]:
        c.print(f"  [red]✗[/red] {' + '.join(x['cards'])} ({x['reason']})")


def _trailing_blank(style: str) -> Callable[[Console, Notice], None]:
    def render(c: Console, n: Notice) -> None:
        c.print(styled(n.message, style) + "\n")
    return render


def _leading_blank(style: str) -> Callable[[Console, Notice], None]:
    def render(c: Console, n: Notice) -> None:
        c.print("\n" + styled(n.message, style))
    return render


def _shortfall(c: Console, n: Notice) -> None:
    d = n.data
    c.print(
        f"\n[yellow]Warning: Collection short by {d['shortfall']} cards. "
        f"Deck will have {d['deck_size']} cards instead of 100.[/yellow]"
    )
    c.print(
        f"[yellow]Adding {d['shortfall']} extra lands to fill. "
        f"Consider acquiring more cards in {d['colors']}.[/yellow]\n"
    )


def _validation(c: Console, n: Notice) -> None:
    c.print("[yellow]Validation warnings:[/yellow]")
    for err in n.data["errors"]:
        c.print(f"  [yellow]![/yellow] {err}")
    c.print()


def _explain_started(c: Console, n: Notice) -> None:
    c.print(f"[bold]Explaining:[/bold] {n.data['commander']} ({n.data['card_count']} cards)\n")


def _suggest_started(c: Console, n: Notice) -> None:
    c.print(f"[bold]Suggesting upgrades for:[/bold] {n.data['commander']}")
    c.print(f"[dim]Collection: {n.data['owned_unique']} unique cards owned[/dim]\n")


_RENDERERS: dict[str, Callable[[Console, Notice], None]] = {
    "collection.matched": _matched,
    "collection.fuzzy": _fuzzy,
    "collection.unmatched": _unmatched,
    "commander.auto_selected": _auto_commander,
    "partner.auto_selected": _auto_partner,
    "commander.selected": _commander_selected,
    "bracket.excluded_cards": _bracket_excluded_cards,
    "bracket.excluded_combos": _bracket_excluded_combos,
    "bracket.remaining": _trailing_blank("dim"),
    "candidates.insufficient": _leading_blank("yellow"),
    "candidates.underpowered": _trailing_blank("yellow"),
    "deck.shortfall": _shortfall,
    "deck.validation": _validation,
    "explain.started": _explain_started,
    "suggest.started": _suggest_started,
}


class ConsoleReporter(Reporter):
    """Prints notices as they are reported and shows spinners for progress."""

    def __init__(self, console: Console):
        super().__init__()
        self.console = console

    def emit(self, notice: Notice) -> None:
        renderer = _RENDERERS.get(notice.code)
        if renderer:
            renderer(self.console, notice)
        else:
            self.console.print(styled(notice.message, _LEVEL_STYLE[notice.level]))

    @contextmanager
    def progress(self, description: str) -> Iterator[None]:
        with spinner(self.console, description):
            yield


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def render_error(console: Console, err: CommanderAIError, default_collection=None) -> None:
    if isinstance(err, LLMError):
        console.print(f"[red]Error: {err.message}[/red]")
        return
    console.print(f"[red]{err.message}[/red]")
    for detail in err.details:
        console.print(f"[dim]{detail}[/dim]")
    if isinstance(err, CollectionNotFoundError) and err.data.get("kind") == "collection":
        console.print(
            f"[dim]Pass --collection/-c <file>, or create the default "
            f"{default_collection} (e.g. via `commanderai convert`).[/dim]"
        )
