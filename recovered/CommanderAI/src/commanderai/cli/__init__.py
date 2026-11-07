"""CommanderAI command-line interface (``commanderai`` entry point)."""

from commanderai.cli.commands import app, console

# Backwards-compatible aliases (historically private helpers of cli.py).
from commanderai.services.commanders import (
    auto_select_commander as _auto_select_commander,
)
from commanderai.services.commanders import (
    auto_select_partner as _auto_select_partner,
)

__all__ = ["_auto_select_commander", "_auto_select_partner", "app", "console"]
