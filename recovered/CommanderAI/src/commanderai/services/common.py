"""Option resolution shared by several services (theme, colors, variety)."""

from __future__ import annotations

import random

from commanderai.deckbuilder.colors import resolve_colors
from commanderai.deckbuilder.themes import archetype_names, resolve_theme
from commanderai.deckbuilder.variety import make_rng, resolve_seed
from commanderai.errors import UnknownColorsError, UnknownThemeError
from commanderai.reporting import Reporter


def resolve_theme_or_raise(theme: str | None) -> str | None:
    """Canonical theme key for a theme/tribe/alias, or raise UnknownThemeError."""
    if not theme:
        return None
    canonical = resolve_theme(theme)
    if canonical is None:
        raise UnknownThemeError(
            f"Unknown theme '{theme}'.",
            details=[
                f"Archetypes: {', '.join(archetype_names())}",
                (
                    "Also accepts tribes (elf, goblin, dragon, sliver...) and aliases "
                    "(go-wide, storm, bogles, tron, death-and-taxes...)."
                ),
            ],
            theme=theme,
        )
    return canonical


def resolve_colors_or_raise(colors: str | None) -> set[str] | None:
    """Color-identity set for WUBRG letters / a combination name, or raise."""
    if not colors:
        return None
    resolved = resolve_colors(colors)
    if resolved is None:
        raise UnknownColorsError(
            f"Unknown colors '{colors}'. Use WUBRG letters (e.g. WUB) or a "
            f"combination name (e.g. esper, jund, azorius, five-color).",
            colors=colors,
        )
    return resolved


class VarietySetup:
    """Resolved variety settings: effective level, seed used, and the RNG."""

    def __init__(self, variety: float, seed: int | None, rng: random.Random | None):
        self.variety = variety
        self.seed = seed
        self.rng = rng

    @property
    def enabled(self) -> bool:
        return self.rng is not None


def setup_variety(variety: float, seed: int | None, reporter: Reporter) -> VarietySetup:
    """Resolve variety + RNG. Passing a seed alone implies moderate variety (0.5).

    Reports the seed used so any variety run can be reproduced. When fully
    deterministic, returns variety 0.0 and no RNG.
    """
    effective = variety
    if seed is not None and variety == 0.0:
        effective = 0.5
    if effective <= 0:
        return VarietySetup(0.0, None, None)
    resolved = resolve_seed(seed)
    reporter.detail(
        "variety.seed",
        f"Variety {effective:.2f} (seed {resolved} — reuse with --seed {resolved})",
        variety=effective,
        seed=resolved,
    )
    return VarietySetup(effective, resolved, make_rng(resolved))
