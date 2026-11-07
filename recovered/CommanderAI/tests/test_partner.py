from commanderai.deckbuilder.partner import (
    can_partner,
    combined_identity,
    merge_commanders,
    partner_ability,
)
from commanderai.deckbuilder.rules import validate_deck
from commanderai.models import Card, DeckPick, DeckSlot


def _card(name, type_line, colors, text="", keywords=None):
    return Card(
        name=name,
        type_line=type_line,
        color_identity=colors,
        oracle_text=text,
        keywords=keywords or [],
    )


def _plain_partner(name, colors):
    return _card(
        name, "Legendary Creature — Human", colors,
        text="Partner (You can have two commanders if both have partner.)",
        keywords=["Partner"],
    )


def test_plain_partner_pairs():
    a = _plain_partner("Thrasios", ["G", "U"])
    b = _plain_partner("Tymna", ["W", "B"])
    assert can_partner(a, b)
    assert combined_identity(a, b) == {"G", "U", "W", "B"}


def test_partner_with_only_matches_named():
    kydele = _card(
        "Kydele, Chosen of Kruphix", "Legendary Creature — Human", ["G", "U"],
        text="Partner with Thrasios, Triton Hero (When this creature enters, ...)",
        keywords=["Partner with"],
    )
    thrasios = _card(
        "Thrasios, Triton Hero", "Legendary Creature — Merfolk", ["G", "U"],
        text="Partner with Kydele, Chosen of Kruphix (When this creature enters, ...)",
        keywords=["Partner with"],
    )
    other = _plain_partner("Tymna", ["W", "B"])
    assert can_partner(kydele, thrasios)
    assert not can_partner(kydele, other)


def test_background_pairing():
    chooser = _card(
        "Wilson, Refined Grizzly", "Legendary Creature — Bear", ["G"],
        text="Choose a Background (You can have a Background as a second commander.)",
        keywords=["Choose a background"],
    )
    background = _card(
        "Candlekeep Sage", "Legendary Enchantment — Background", ["U"],
        text="Commander creatures you own have ...",
    )
    plain = _plain_partner("Thrasios", ["G", "U"])
    assert can_partner(chooser, background)
    assert can_partner(background, chooser)
    assert not can_partner(chooser, plain)


def test_doctor_companion_pairing():
    companion = _card(
        "Cassandra", "Legendary Creature — Human", ["W"],
        text="Doctor's companion (You can have two commanders if the other is a Time Lord Doctor.)",
        keywords=["Doctor's companion"],
    )
    doctor = _card("The Tenth Doctor", "Legendary Creature — Time Lord Doctor", ["U", "R"])
    assert can_partner(companion, doctor)


def test_friends_forever_pairing():
    a = _card("Will", "Legendary Creature — Human", ["G"], text="Friends forever (...)")
    b = _card("Mike", "Legendary Creature — Human", ["U"], text="Friends forever (...)")
    assert can_partner(a, b)


def test_no_partner_ability():
    a = _card("Atraxa", "Legendary Creature — Phyrexian Angel", ["W", "U", "B", "G"])
    assert not partner_ability(a).can_take_partner


def test_merge_commanders_union():
    a = _plain_partner("A", ["G", "U"])
    b = _plain_partner("B", ["W"])
    merged = merge_commanders(a, b)
    assert set(merged.color_identity) == {"G", "U", "W"}


def test_validate_deck_partner_requires_98():
    a = _plain_partner("A", ["B"])
    b = _plain_partner("B", ["W"])
    picks = [
        DeckPick(card=_card(f"Card {i}", "Creature", ["B"]), slot=DeckSlot.UTILITY)
        for i in range(98)
    ]
    errors = validate_deck(a, picks, partner=b)
    assert errors == []
    # 99 picks should now be wrong for a 2-commander deck
    picks99 = picks + [DeckPick(card=_card("Extra", "Creature", ["W"]), slot=DeckSlot.UTILITY)]
    assert any("need exactly 98" in e for e in validate_deck(a, picks99, partner=b))


def test_validate_deck_partner_union_identity():
    a = _plain_partner("A", ["B"])
    b = _plain_partner("B", ["W"])
    # A red card is outside the W/B identity
    picks = [DeckPick(card=_card("Red Card", "Creature", ["R"]), slot=DeckSlot.THREAT)]
    picks += [
        DeckPick(card=_card(f"C{i}", "Creature", ["W"]), slot=DeckSlot.UTILITY)
        for i in range(97)
    ]
    errors = validate_deck(a, picks, partner=b)
    assert any("Red Card" in e for e in errors)
