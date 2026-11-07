from commanderai.deckbuilder.budget import (
    card_price,
    deck_price,
    enforce_budget,
    filter_candidates_by_budget,
)
from commanderai.models import Card, DeckPick, DeckSlot, ScoredCard


def _make_card(name, price=None, type_line="Creature", color_identity=None, mana_cost=""):
    prices = {"usd": str(price)} if price is not None else {}
    return Card(
        name=name,
        type_line=type_line,
        color_identity=color_identity if color_identity is not None else ["G"],
        mana_cost=mana_cost,
        prices=prices,
    )


def _scored(card, slot=DeckSlot.THREAT, score=10.0):
    return ScoredCard(card=card, score=score, slot=slot)


def test_card_price_parses_usd():
    assert card_price(_make_card("A", price="12.50")) == 12.50


def test_card_price_unknown_is_zero():
    assert card_price(_make_card("A", price=None)) == 0.0
    assert card_price(_make_card("A", price="")) == 0.0


def test_card_price_falls_back_to_foil():
    card = Card(name="Foil", prices={"usd": None, "usd_foil": "5.00"})
    assert card_price(card) == 5.00


def test_filter_candidates_drops_over_budget():
    candidates = {
        DeckSlot.THREAT: [
            _scored(_make_card("Cheap", price="2")),
            _scored(_make_card("Pricey", price="50")),
        ],
    }
    filtered, removed = filter_candidates_by_budget(candidates, budget=10)
    names = [sc.card.name for sc in filtered[DeckSlot.THREAT]]
    assert names == ["Cheap"]
    assert removed == 1


def test_enforce_budget_swaps_to_cheaper_candidate():
    commander = _make_card("Cmdr", type_line="Legendary Creature")
    expensive = _make_card("Expensive", price="40")
    cheap = _make_card("Cheap", price="1")
    picks = [DeckPick(card=expensive, slot=DeckSlot.THREAT)]
    candidates = {DeckSlot.THREAT: [_scored(expensive), _scored(cheap)]}

    new_picks, swaps, final = enforce_budget(picks, candidates, commander, budget=10)

    assert swaps == 1
    assert new_picks[0].card.name == "Cheap"
    assert final <= 10


def test_enforce_budget_downgrades_nonbasic_land_to_basic():
    commander = _make_card("Cmdr", type_line="Legendary Creature", color_identity=["G"])
    dual = _make_card(
        "Fancy Land", price="30", type_line="Land", color_identity=["G"]
    )
    picks = [DeckPick(card=dual, slot=DeckSlot.LAND)]

    new_picks, swaps, final = enforce_budget(picks, {}, commander, budget=5)

    assert swaps == 1
    assert "basic" in new_picks[0].card.type_line.lower()
    assert final == 0.0


def test_enforce_budget_reports_when_unreachable():
    commander = _make_card("Cmdr", type_line="Legendary Creature")
    # No cheaper alternatives available; single pick already over budget.
    expensive = _make_card("Expensive", price="40")
    picks = [DeckPick(card=expensive, slot=DeckSlot.THREAT)]

    new_picks, swaps, final = enforce_budget(picks, {}, commander, budget=10)

    assert swaps == 0
    assert final == 40.0
    assert deck_price(new_picks) == 40.0
