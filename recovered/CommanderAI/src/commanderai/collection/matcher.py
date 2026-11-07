import difflib

from commanderai.data.card_index import CardIndex
from commanderai.models import Card, CollectionEntry


_SKIP_NAMES = {
    "double-faced substitute card",
}

_SKIP_PATTERNS = [
    "token",
    "emblem",
    "plane —",
    "phenomenon",
]


class MatchResult:
    def __init__(self):
        self.matched: list[CollectionEntry] = []
        self.unmatched: list[str] = []
        self.fuzzy_matched: list[tuple[str, str]] = []
        self.skipped_tokens: list[str] = []


def _is_likely_token_or_special(name: str) -> bool:
    lower = name.lower()
    if lower in _SKIP_NAMES:
        return True
    # Single-word names are almost always tokens (Assassin, Elemental, Spirit, etc.)
    if " " not in name and len(name) > 2 and "'" not in name:
        return True
    # Common token indicators
    if "—" in name and len(name.split("—")[0].strip().split()) <= 2:
        return True
    return False


def match_collection(entries: list[CollectionEntry], index: CardIndex) -> MatchResult:
    result = MatchResult()
    all_names = list(index.by_name_lower.keys())

    for entry in entries:
        card = index.get(entry.card_name)
        if card:
            entry.card = card
            result.matched.append(entry)
            continue

        if entry.card_name.lower() in index.non_legal_names:
            result.skipped_tokens.append(entry.card_name)
            continue

        close = difflib.get_close_matches(
            entry.card_name.lower(), all_names, n=1, cutoff=0.90
        )
        if close:
            card = index.by_name_lower[close[0]]
            entry.card = card
            result.matched.append(entry)
            result.fuzzy_matched.append((entry.card_name, card.name))
        elif _is_likely_token_or_special(entry.card_name):
            result.skipped_tokens.append(entry.card_name)
        else:
            result.unmatched.append(entry.card_name)

    return result


def get_unique_cards(entries: list[CollectionEntry]) -> list[Card]:
    seen: set[str] = set()
    cards: list[Card] = []
    for entry in entries:
        if entry.card and entry.card.name not in seen:
            seen.add(entry.card.name)
            cards.append(entry.card)
    return cards
