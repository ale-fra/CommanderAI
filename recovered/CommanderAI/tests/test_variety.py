from commanderai.deckbuilder.candidates import heuristic_pick
from commanderai.deckbuilder.scoring import score_card
from commanderai.deckbuilder.themes import theme_hits, theme_names
from commanderai.deckbuilder.variety import (
    make_rng,
    softmax_weights,
    weighted_sample_without_replacement,
)
from commanderai.models import Card, DeckSlot, ScoredCard


def _scored(name, score, slot=DeckSlot.THREAT):
    return ScoredCard(
        card=Card(name=name, oracle_text=""),
        score=score,
        slot=slot,
    )


def _candidates(n_per_slot=12):
    cands = {}
    for slot in DeckSlot:
        if slot == DeckSlot.LAND:
            cands[slot] = []
            continue
        cands[slot] = [
            _scored(f"{slot.value}-{i}", score=100 - i, slot=slot)
            for i in range(n_per_slot)
        ]
    return cands


def test_weighted_sample_respects_k_and_uniqueness():
    rng = make_rng(1)
    items = list("abcdefgh")
    weights = [1.0] * len(items)
    out = weighted_sample_without_replacement(rng, items, weights, 4)
    assert len(out) == 4
    assert len(set(out)) == 4


def test_weighted_sample_is_seed_reproducible():
    items = list(range(20))
    weights = [float(i + 1) for i in items]
    a = weighted_sample_without_replacement(make_rng(7), items, weights, 5)
    b = weighted_sample_without_replacement(make_rng(7), items, weights, 5)
    assert a == b


def test_softmax_low_variety_favors_top():
    weights = softmax_weights([100.0, 50.0, 0.0], variety=0.05)
    assert weights[0] > weights[1] > weights[2]
    # top should dominate heavily at low variety
    assert weights[0] / sum(weights) > 0.9


def test_heuristic_variety_zero_is_deterministic_top_n():
    cands = _candidates()
    rng = make_rng(123)
    picked = heuristic_pick(cands, land_count=37, rng=rng, variety=0.0)
    # variety=0 must equal strict top-N regardless of rng
    threat = [sc.card.name for sc in picked[DeckSlot.THREAT]]
    assert threat == [f"THREAT-{i}" for i in range(len(threat))]


def test_heuristic_same_seed_same_deck():
    cands = _candidates()
    a = heuristic_pick(cands, land_count=37, rng=make_rng(99), variety=0.7)
    b = heuristic_pick(cands, land_count=37, rng=make_rng(99), variety=0.7)
    names_a = sorted(sc.card.name for v in a.values() for sc in v)
    names_b = sorted(sc.card.name for v in b.values() for sc in v)
    assert names_a == names_b


def test_heuristic_different_seed_differs():
    cands = _candidates()
    a = heuristic_pick(cands, land_count=37, rng=make_rng(1), variety=0.9)
    b = heuristic_pick(cands, land_count=37, rng=make_rng(2), variety=0.9)
    names_a = {sc.card.name for v in a.values() for sc in v}
    names_b = {sc.card.name for v in b.values() for sc in v}
    assert names_a != names_b


def test_theme_bonus_changes_score():
    commander = Card(name="Cmdr", oracle_text="")
    sac_card = Card(name="Sac Outlet", oracle_text="Sacrifice a creature: draw a card.")
    base = score_card(sac_card, commander)
    themed = score_card(sac_card, commander, theme="aristocrats")
    assert themed.score > base.score
    assert any("aristocrats" in r for r in themed.reasons)


def test_theme_hits_and_names():
    assert "aristocrats" in theme_names()
    assert theme_hits("tokens", "Create a 1/1 white Soldier creature token.") >= 1
    assert theme_hits("tokens", "Draw a card.") == 0
