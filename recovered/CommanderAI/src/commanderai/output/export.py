from commanderai.models import Deck, DeckSlot


def export_text(deck: Deck) -> str:
    lines = [f"1 {c.name}" for c in deck.commanders]
    for pick in deck.cards:
        lines.append(f"1 {pick.card.name}")
    return "\n".join(lines)


def export_mtgo(deck: Deck) -> str:
    return export_text(deck)


def export_moxfield(deck: Deck) -> str:
    lines = [f"1 {c.name} *CMDR*" for c in deck.commanders]
    for pick in deck.cards:
        lines.append(f"1 {pick.card.name}")
    return "\n".join(lines)


def export_archidekt(deck: Deck) -> str:
    lines = [f"1 {c.name} [Commander]" for c in deck.commanders]
    for pick in deck.cards:
        category = pick.slot.value.capitalize()
        lines.append(f"1 {pick.card.name} [{category}]")
    return "\n".join(lines)


def export_deck(deck: Deck, fmt: str) -> str:
    exporters = {
        "text": export_text,
        "mtgo": export_mtgo,
        "moxfield": export_moxfield,
        "archidekt": export_archidekt,
    }
    exporter = exporters.get(fmt)
    if not exporter:
        raise ValueError(f"Unknown format '{fmt}'. Options: {list(exporters.keys())}")
    return exporter(deck)
