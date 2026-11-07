import random

from commanderai.config import CANDIDATES_PER_SLOT_MULTIPLIER, MAX_TOTAL_CANDIDATES, SLOT_QUOTAS
from commanderai.models import Card, DeckSlot, ScoredCard
from commanderai.deckbuilder.partner import merge_commanders
from commanderai.deckbuilder.scoring import score_card
from commanderai.deckbuilder.slots import classify_card
from commanderai.deckbuilder.variety import softmax_weights, weighted_sample_without_replacement


def build_candidates(
    collection_cards: list[Card],
    commander: Card,
    theme: str | None = None,
    synergy_emphasis: float = 1.0,
    rank_emphasis: float = 1.0,
    partner: Card | None = None,
    quotas: dict[str, int] | None = None,
) -> dict[DeckSlot, list[ScoredCard]]:
    # When there's a partner, score against the combined color identity and the
    # union of both commanders' text/keywords.
    scoring_commander = merge_commanders(commander, partner) if partner else commander
    identity = set(scoring_commander.color_identity)
    exclude = {commander.name} | ({partner.name} if partner else set())

    legal_cards = [
        c for c in collection_cards
        if set(c.color_identity).issubset(identity) and c.name not in exclude
    ]

    by_slot: dict[DeckSlot, list[ScoredCard]] = {slot: [] for slot in DeckSlot}

    for card in legal_cards:
        slot = classify_card(card)
        scored = score_card(
            card, scoring_commander, slot,
            theme=theme, synergy_emphasis=synergy_emphasis, rank_emphasis=rank_emphasis,
        )
        by_slot[slot].append(scored)

    for slot in by_slot:
        by_slot[slot].sort(key=lambda s: s.score, reverse=True)

    trimmed = _trim_candidates(by_slot, quotas or SLOT_QUOTAS)
    return trimmed


def _trim_candidates(
    by_slot: dict[DeckSlot, list[ScoredCard]],
    quotas: dict[str, int],
) -> dict[DeckSlot, list[ScoredCard]]:
    trimmed: dict[DeckSlot, list[ScoredCard]] = {}
    total = 0

    for slot in DeckSlot:
        quota = quotas.get(slot.value, 10)
        max_for_slot = quota * CANDIDATES_PER_SLOT_MULTIPLIER
        candidates = by_slot.get(slot, [])[:max_for_slot]
        trimmed[slot] = candidates
        total += len(candidates)

    if total > MAX_TOTAL_CANDIDATES:
        ratio = MAX_TOTAL_CANDIDATES / total
        for slot in trimmed:
            new_len = max(1, int(len(trimmed[slot]) * ratio))
            trimmed[slot] = trimmed[slot][:new_len]

    return trimmed


def _select_from_slot(
    available: list[ScoredCard],
    quota: int,
    rng: random.Random | None,
    variety: float,
) -> list[ScoredCard]:
    """Top-N when deterministic; score-weighted sample when variety > 0."""
    if variety <= 0 or rng is None or len(available) <= quota:
        return available[:quota]
    weights = softmax_weights([sc.score for sc in available], variety)
    sampled = weighted_sample_without_replacement(rng, available, weights, quota)
    sampled.sort(key=lambda s: s.score, reverse=True)
    return sampled


def heuristic_pick(
    candidates: dict[DeckSlot, list[ScoredCard]],
    land_count: int = 37,
    rng: random.Random | None = None,
    variety: float = 0.0,
    others: int = 99,
    quotas: dict[str, int] | None = None,
) -> dict[DeckSlot, list[ScoredCard]]:
    """Pick non-land cards. ``others`` is the count of non-commander cards in the
    deck (99 for a single commander, 98 when there's a partner)."""
    quotas = quotas or SLOT_QUOTAS
    picks: dict[DeckSlot, list[ScoredCard]] = {}

    for slot in DeckSlot:
        if slot == DeckSlot.LAND:
            continue
        quota = quotas.get(slot.value, 10)
        available = candidates.get(slot, [])
        picks[slot] = _select_from_slot(available, quota, rng, variety)

    total_nonland = sum(len(v) for v in picks.values())
    target_nonland = others - land_count

    if total_nonland < target_nonland:
        deficit = target_nonland - total_nonland
        all_remaining = []
        for slot, scored_list in candidates.items():
            if slot == DeckSlot.LAND:
                continue
            picked_names = {s.card.name for s in picks.get(slot, [])}
            for s in scored_list:
                if s.card.name not in picked_names:
                    all_remaining.append(s)
        all_remaining.sort(key=lambda s: s.score, reverse=True)
        if variety > 0 and rng is not None and len(all_remaining) > deficit:
            weights = softmax_weights([s.score for s in all_remaining], variety)
            extra = weighted_sample_without_replacement(rng, all_remaining, weights, deficit)
        else:
            extra = all_remaining[:deficit]
        for s in extra:
            picks.setdefault(s.slot, []).append(s)

    elif total_nonland > target_nonland:
        excess = total_nonland - target_nonland
        all_picks_flat = []
        for slot, scored_list in picks.items():
            for s in scored_list:
                all_picks_flat.append((slot, s))
        all_picks_flat.sort(key=lambda x: x[1].score)
        to_remove = all_picks_flat[:excess]
        for slot, s in to_remove:
            picks[slot].remove(s)

    return picks
