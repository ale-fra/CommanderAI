from commanderai.models import Card, DeckPick, DeckSlot
from commanderai.deckbuilder.rules import (
    color_identity_filter,
    is_legal_commander,
    validate_deck,
)


def _make_card(name="Test", type_line="Creature", color_identity=None, oracle_text=""):
    return Card(
        name=name,
        type_line=type_line,
        color_identity=color_identity or [],
        oracle_text=oracle_text,
    )


def test_legendary_creature_is_commander():
    card = _make_card(type_line="Legendary Creature — Human Wizard")
    assert is_legal_commander(card) is True


def test_regular_creature_not_commander():
    card = _make_card(type_line="Creature — Elf Warrior")
    assert is_legal_commander(card) is False


def test_planeswalker_with_text_is_commander():
    card = _make_card(
        type_line="Legendary Planeswalker — Teferi",
        oracle_text="Teferi can be your commander.",
    )
    assert is_legal_commander(card) is True


def test_color_identity_filter():
    commander = _make_card(color_identity=["W", "U", "B", "G"])
    cards = [
        _make_card(name="WUB card", color_identity=["W", "U", "B"]),
        _make_card(name="Red card", color_identity=["R"]),
        _make_card(name="Colorless", color_identity=[]),
        _make_card(name="Full WUBG", color_identity=["W", "U", "B", "G"]),
    ]
    filtered = color_identity_filter(cards, commander)
    names = [c.name for c in filtered]
    assert "WUB card" in names
    assert "Colorless" in names
    assert "Full WUBG" in names
    assert "Red card" not in names


def test_validate_deck_singleton():
    commander = _make_card(name="Commander", color_identity=["W"])
    picks = [
        DeckPick(card=_make_card(name=f"Card {i}", color_identity=["W"]), slot=DeckSlot.UTILITY)
        for i in range(97)
    ]
    picks.append(DeckPick(card=_make_card(name="Dupe", color_identity=["W"]), slot=DeckSlot.UTILITY))
    picks.append(DeckPick(card=_make_card(name="Dupe", color_identity=["W"]), slot=DeckSlot.UTILITY))
    errors = validate_deck(commander, picks)
    assert any("Duplicate" in e for e in errors)
