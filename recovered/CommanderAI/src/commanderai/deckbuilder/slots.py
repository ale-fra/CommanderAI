import re

from commanderai.models import Card, DeckSlot

_RAMP_PATTERNS = [
    re.compile(r"add \{[WUBRGC]", re.IGNORECASE),
    re.compile(r"add .* mana", re.IGNORECASE),
    re.compile(r"search your library for a.*land.*put.*onto the battlefield", re.IGNORECASE),
    re.compile(r"you may play an additional land", re.IGNORECASE),
]

_DRAW_PATTERNS = [
    re.compile(r"draw (?:a card|cards|\d+ cards|two cards|three cards)", re.IGNORECASE),
    re.compile(r"whenever.*draw", re.IGNORECASE),
    re.compile(r"look at the top.*put.*into your hand", re.IGNORECASE),
]

_REMOVAL_PATTERNS = [
    re.compile(r"destroy target (?!land)(?!player)", re.IGNORECASE),
    re.compile(r"exile target", re.IGNORECASE),
    re.compile(r"deals? \d+ damage to (?:target|any)", re.IGNORECASE),
    re.compile(r"return target.*to.*(?:hand|owner)", re.IGNORECASE),
    re.compile(r"target.*gets? -\d+/-\d+", re.IGNORECASE),
]

_WIPE_PATTERNS = [
    re.compile(r"destroy all (?:creature|nonland|permanent|artifact)", re.IGNORECASE),
    re.compile(r"exile all (?:creature|nonland|permanent)", re.IGNORECASE),
    re.compile(r"all creatures get -\d+/-\d+", re.IGNORECASE),
    re.compile(r"deals? \d+ damage to each creature", re.IGNORECASE),
    re.compile(r"each (?:opponent|player) sacrifices", re.IGNORECASE),
]


def classify_card(card: Card) -> DeckSlot:
    type_line = card.type_line.lower()

    if "land" in type_line and "creature" not in type_line:
        return DeckSlot.LAND

    text = card.oracle_text or ""

    for pattern in _WIPE_PATTERNS:
        if pattern.search(text):
            return DeckSlot.WIPE

    for pattern in _REMOVAL_PATTERNS:
        if pattern.search(text):
            return DeckSlot.REMOVAL

    for pattern in _RAMP_PATTERNS:
        if pattern.search(text):
            return DeckSlot.RAMP

    for pattern in _DRAW_PATTERNS:
        if pattern.search(text):
            return DeckSlot.DRAW

    if _is_threat(card):
        return DeckSlot.THREAT

    return DeckSlot.UTILITY


def _is_threat(card: Card) -> bool:
    type_line = card.type_line.lower()
    if "planeswalker" in type_line:
        return True
    if "creature" in type_line and card.power:
        try:
            if int(card.power) >= 4:
                return True
        except ValueError:
            pass
    return False
