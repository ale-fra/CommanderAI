"""Budget-aware deck construction helpers.

The ``--budget`` flag caps the deck's total estimated USD price — all 100 cards,
**commanders included** — using one price rule everywhere (``Card.price_usd``:
nonfoil, else foil, else etched; unknown = 0). Budget is enforced in three stages:

1. ``filter_candidates_by_budget`` removes any single candidate that already
   exceeds what is left of the budget after paying for the commander(s), so
   neither the heuristic nor the LLM can pick a card that can never fit.
2. The LLM is told the budget via an extra instruction (prices are already in
   the prompt).
3. ``enforce_budget`` runs after the full deck is assembled and greedily swaps
   the most expensive cards for cheaper alternatives until the deck fits — or
   reports that the budget could not be met with the available pool.
"""

from commanderai.deckbuilder.mana_base import count_pips, make_basic_land
from commanderai.models import Card, DeckPick, DeckSlot, ScoredCard


def card_price(card: Card) -> float:
    """Best-effort USD price for a card; 0.0 when unknown (e.g. basics)."""
    return card.price_usd or 0.0


def deck_price(picks: list[DeckPick], commanders: list[Card] | None = None) -> float:
    """Price of the picks plus (optionally) the commanders."""
    return sum(card_price(p.card) for p in picks) + sum(card_price(c) for c in commanders or [])


def commanders_price(commander: Card, partner: Card | None = None) -> float:
    return card_price(commander) + (card_price(partner) if partner else 0.0)


def filter_candidates_by_budget(
    candidates: dict[DeckSlot, list[ScoredCard]], budget: float
) -> tuple[dict[DeckSlot, list[ScoredCard]], int]:
    """Drop candidates whose individual price exceeds ``budget``.

    Callers pass the budget *remaining after the commanders*. Returns the
    filtered candidates and the number of cards removed.
    """
    filtered: dict[DeckSlot, list[ScoredCard]] = {}
    removed = 0
    for slot, scored in candidates.items():
        kept = [sc for sc in scored if card_price(sc.card) <= budget]
        removed += len(scored) - len(kept)
        filtered[slot] = kept
    return filtered, removed


def _is_basic_land(card: Card) -> bool:
    type_line = card.type_line.lower()
    return "basic" in type_line and "land" in type_line


def enforce_budget(
    picks: list[DeckPick],
    candidates: dict[DeckSlot, list[ScoredCard]],
    commander: Card,
    budget: float,
    partner: Card | None = None,
) -> tuple[list[DeckPick], int, float]:
    """Greedily reduce the deck's total price (commanders included) to ``budget``.

    - Non-land picks are swapped for the cheapest unused same-slot candidate
      that lowers the price.
    - Non-basic lands are downgraded to basic lands (≈free) of a color the deck
      uses.

    At each step the swap that saves the most money is applied. Returns the
    (possibly modified) picks, the number of swaps made, and the final price
    of the whole deck including the commander(s).
    """
    picks = list(picks)
    commanders = [commander] + ([partner] if partner else [])
    identity = set(commander.color_identity)
    if partner:
        identity |= set(partner.color_identity)

    picked_names = {p.card.name for p in picks}
    pool: dict[DeckSlot, list[Card]] = {}
    for slot, scored in candidates.items():
        affordable = [sc.card for sc in scored if sc.card.name not in picked_names]
        affordable.sort(key=card_price)
        pool[slot] = affordable

    swaps = 0
    while deck_price(picks, commanders) > budget:
        best: tuple[float, int, Card] | None = None  # (savings, idx, replacement)

        for i, pick in enumerate(picks):
            current = card_price(pick.card)
            if current <= 0:
                continue

            if pick.slot == DeckSlot.LAND:
                if _is_basic_land(pick.card):
                    continue
                basic = _basic_for_deck(picks, commander, identity)
                if basic is None:
                    continue
                savings = current - card_price(basic)
                replacement = basic
            else:
                replacement = next(
                    (c for c in pool.get(pick.slot, []) if card_price(c) < current),
                    None,
                )
                if replacement is None:
                    continue
                savings = current - card_price(replacement)

            if savings <= 0:
                continue
            if best is None or savings > best[0]:
                best = (savings, i, replacement)

        if best is None:
            break  # no beneficial swap available

        _, idx, replacement = best
        old = picks[idx]
        picks[idx] = DeckPick(
            card=replacement,
            slot=old.slot,
            reason=f"budget swap (was {old.card.name})",
        )
        if old.slot in pool:
            pool[old.slot] = [c for c in pool[old.slot] if c.name != replacement.name]
        swaps += 1

    return picks, swaps, deck_price(picks, commanders)


def _basic_for_deck(
    picks: list[DeckPick], commander: Card, identity: set[str]
) -> Card | None:
    """Pick a basic land for the deck's most-needed color in the identity."""
    if not identity:
        return None
    nonland = [p.card for p in picks if p.slot != DeckSlot.LAND]
    pips = count_pips(nonland + [commander])
    color = max(identity, key=lambda c: pips.get(c, 0))
    return make_basic_land(color)
