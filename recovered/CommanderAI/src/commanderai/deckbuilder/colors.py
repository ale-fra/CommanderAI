"""MTG color-combination names (guilds, shards, wedges, four-color, WUBRG).

Lets `--colors` accept either raw color letters (``WUB``) or a combination name
(``esper``, ``jund``, ``azorius``, ``five-color`` ...).
"""

COLOR_NAMES: dict[str, str] = {
    # Mono
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
    "colorless": "",
    # Guilds (two-color)
    "azorius": "WU",
    "dimir": "UB",
    "rakdos": "BR",
    "gruul": "RG",
    "selesnya": "GW",
    "orzhov": "WB",
    "izzet": "UR",
    "golgari": "BG",
    "boros": "RW",
    "simic": "GU",
    # Shards & wedges (three-color)
    "esper": "WUB",
    "grixis": "UBR",
    "jund": "BRG",
    "naya": "RGW",
    "bant": "GWU",
    "jeskai": "WUR",
    "sultai": "UBG",
    "mardu": "BRW",
    "temur": "RGU",
    "abzan": "GWB",
    # Four-color (Nephilim names)
    "yore-tiller": "WUBR",
    "glint-eye": "UBRG",
    "dune-brood": "BRGW",
    "ink-treader": "RGWU",
    "witch-maw": "GWUB",
    "non-white": "UBRG",
    "non-blue": "BRGW",
    "non-black": "RGWU",
    "non-red": "GWUB",
    "non-green": "WUBR",
    # Five-color
    "five-color": "WUBRG",
    "5c": "WUBRG",
    "wubrg": "WUBRG",
    "rainbow": "WUBRG",
}

_VALID_LETTERS = set("WUBRG")
_WUBRG_ORDER = "WUBRG"


def wubrg_sort(colors) -> list[str]:
    """Sort color letters into canonical WUBRG order (non-colors last)."""
    return sorted(colors, key=lambda c: _WUBRG_ORDER.index(c) if c in _WUBRG_ORDER else 99)


def format_colors(colors, empty: str = "C") -> str:
    """Render a color identity as WUBRG-ordered letters (``empty`` if colorless)."""
    return "".join(wubrg_sort(colors)) or empty


def color_name(identity: set[str]) -> str:
    """Return the combination name for a color-identity set, if one exists."""
    letters = "".join(sorted(identity, key="WUBRG".index))
    for name, combo in COLOR_NAMES.items():
        if combo and set(combo) == identity and "-" not in name and name not in (
            "5c", "wubrg", "rainbow",
        ):
            return name
    return letters or "colorless"


def resolve_colors(value: str | None) -> set[str] | None:
    """Parse ``--colors`` input into a color-identity set.

    Accepts a combination name (case-insensitive) or a string of WUBRG letters.
    Returns None for unrecognised input.
    """
    if not value:
        return None
    key = value.strip().lower().replace(" ", "-")
    if key in COLOR_NAMES:
        return set(COLOR_NAMES[key])
    letters = value.strip().upper()
    if letters and all(ch in _VALID_LETTERS for ch in letters):
        return set(letters)
    return None
