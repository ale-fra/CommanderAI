"""Reference vocabularies accepted by the builder (for CLI `list` and UI pickers)."""

from __future__ import annotations

from pydantic import Field

from commanderai.deckbuilder.colors import COLOR_NAMES
from commanderai.deckbuilder.themes import ALIASES, THEME_QUOTA_DELTAS, TRIBES, archetype_names
from commanderai.models import PublicModel

EXPORT_FORMATS: dict[str, str] = {
    "text": "Plain '1 Card' list (default)",
    "mtgo": "MTGO-compatible list",
    "moxfield": "Moxfield import (commanders tagged *CMDR*)",
    "archidekt": "Archidekt import (cards tagged by slot)",
}

BRACKET_DESCRIPTIONS: dict[int, str] = {
    1: "Exhibition — no game changers, combos, extra turns, or MLD",
    2: "Core — no game changers, no two-card combos, no extra turns/MLD",
    3: "Upgraded — up to 3 game changers, 1 late combo (≥6 mana)",
    4: "Optimized — no restrictions (banlist only)",
    5: "cEDH — full power, no filtering applied",
}

# Grouped color names for readable output.
COLOR_GROUPS: list[tuple[str, list[str]]] = [
    ("Mono", ["white", "blue", "black", "red", "green"]),
    ("Guilds (2)", ["azorius", "dimir", "rakdos", "gruul", "selesnya",
                    "orzhov", "izzet", "golgari", "boros", "simic"]),
    ("Shards & Wedges (3)", ["esper", "grixis", "jund", "naya", "bant",
                             "jeskai", "sultai", "mardu", "temur", "abzan"]),
    ("Four-color", ["yore-tiller", "glint-eye", "dune-brood", "ink-treader", "witch-maw"]),
    ("Five-color", ["five-color"]),
]


class ColorOption(PublicModel):
    name: str
    letters: str


class ColorGroup(PublicModel):
    group: str
    colors: list[ColorOption]


class ThemeOption(PublicModel):
    name: str
    kind: str                               # "archetype" | "tribe"
    quota_deltas: dict[str, int] = Field(default_factory=dict)


class AliasOption(PublicModel):
    alias: str
    target: str


class Vocabulary(PublicModel):
    colors: list[ColorGroup]
    archetypes: list[ThemeOption]
    tribes: list[ThemeOption]
    aliases: list[AliasOption]
    formats: dict[str, str]
    brackets: dict[int, str]


def color_groups() -> list[ColorGroup]:
    return [
        ColorGroup(group=group, colors=[ColorOption(name=n, letters=COLOR_NAMES.get(n, "")) for n in names])
        for group, names in COLOR_GROUPS
    ]


def archetypes() -> list[ThemeOption]:
    return [
        ThemeOption(name=n, kind="archetype", quota_deltas=THEME_QUOTA_DELTAS.get(n, {}))
        for n in archetype_names()
    ]


def tribes() -> list[ThemeOption]:
    from commanderai.deckbuilder.themes import _TRIBAL_DELTAS

    return [ThemeOption(name=t, kind="tribe", quota_deltas=dict(_TRIBAL_DELTAS)) for t in sorted(TRIBES)]


def aliases() -> list[AliasOption]:
    return [AliasOption(alias=a, target=ALIASES[a]) for a in sorted(ALIASES)]


def vocabulary() -> Vocabulary:
    return Vocabulary(
        colors=color_groups(),
        archetypes=archetypes(),
        tribes=tribes(),
        aliases=aliases(),
        formats=dict(EXPORT_FORMATS),
        brackets=dict(BRACKET_DESCRIPTIONS),
    )
