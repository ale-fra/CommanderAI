from commanderai.models import Deck, DeckPick, DeckSlot


def format_deck(deck: Deck, verbose: bool = False) -> str:
    lines: list[str] = []

    label = "Commanders" if deck.partner else "Commander"
    lines.append(f"=== {label}: {' + '.join(c.name for c in deck.commanders)} ===")
    for c in deck.commanders:
        lines.append(f"    {c.name} — {c.type_line}  {c.mana_cost}")
    lines.append("")

    if deck.strategy_summary:
        lines.append(f"Strategy: {deck.strategy_summary}")
        lines.append("")

    by_slot: dict[DeckSlot, list[DeckPick]] = {}
    for pick in deck.cards:
        by_slot.setdefault(pick.slot, []).append(pick)

    slot_order = [
        DeckSlot.RAMP,
        DeckSlot.DRAW,
        DeckSlot.REMOVAL,
        DeckSlot.WIPE,
        DeckSlot.THREAT,
        DeckSlot.UTILITY,
        DeckSlot.LAND,
    ]

    for slot in slot_order:
        picks = by_slot.get(slot, [])
        if not picks:
            continue
        lines.append(f"--- {slot.value} ({len(picks)}) ---")
        for pick in sorted(picks, key=lambda p: p.card.cmc):
            entry = f"  1 {pick.card.name}"
            if pick.card.mana_cost:
                entry += f"  {pick.card.mana_cost}"
            if verbose and pick.reason:
                entry += f"  // {pick.reason}"
            lines.append(entry)
        lines.append("")

    lines.append(f"--- Stats ---")
    lines.append(f"  Total cards: {deck.size}")
    lines.append(f"  Avg CMC (nonland): {deck.avg_cmc:.2f}")
    lines.append(f"  Est. price: ${deck.total_price:.2f}")
    lines.append("")

    if deck.upgrade_suggestions:
        lines.append("--- Upgrade Suggestions ---")
        for suggestion in deck.upgrade_suggestions:
            lines.append(f"  - {suggestion}")
        lines.append("")

    return "\n".join(lines)
