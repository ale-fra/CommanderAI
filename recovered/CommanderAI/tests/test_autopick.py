from commanderai.cli import _auto_select_commander, _auto_select_partner
from commanderai.models import Card


def _cmdr(name, colors, text):
    return Card(
        name=name,
        type_line="Legendary Creature — Human",
        color_identity=colors,
        oracle_text=text,
    )


def _card(name, colors, text):
    return Card(name=name, type_line="Creature — Human", color_identity=colors, oracle_text=text)


def test_autopick_prefers_theme_fit_commander():
    aristo = _cmdr("Death Lord", ["B"], "Whenever a creature you control dies, each opponent loses 1 life.")
    drawer = _cmdr("Card Drawer", ["U"], "Draw a card.")
    collection = [
        aristo,
        drawer,
        _card("Sac A", ["B"], "Sacrifice a creature: add B."),
        _card("Sac B", ["B"], "When this creature dies, draw a card."),
        _card("Sac C", ["B"], "Sacrifice a creature: each opponent loses 1 life."),
        _card("Blue thing", ["U"], "Flying."),
    ]
    picked = _auto_select_commander(collection, "aristocrats", None, None, 0.0)
    assert picked is not None
    commander, support, fit = picked
    assert commander.name == "Death Lord"
    assert support >= 3


def test_autopick_respects_color_filter():
    aristo_b = _cmdr("Black Lord", ["B"], "Whenever a creature you control dies, draw a card.")
    aristo_w = _cmdr("White Lord", ["W"], "Whenever a creature you control dies, gain 1 life.")
    collection = [aristo_b, aristo_w, _card("Sac", ["B"], "Sacrifice a creature: add B.")]
    picked = _auto_select_commander(collection, "aristocrats", {"W"}, None, 0.0)
    assert picked is not None
    assert picked[0].name == "White Lord"


def test_autopick_none_when_no_legal_commander():
    collection = [_card("Just a creature", ["G"], "Trample.")]
    assert _auto_select_commander(collection, "tokens", None, None, 0.0) is None


def _partner_cmdr(name, colors):
    return Card(
        name=name,
        type_line="Legendary Creature — Human",
        color_identity=colors,
        oracle_text="Partner (You can have two commanders if both have partner.)",
        keywords=["Partner"],
    )


def test_auto_select_partner_finds_compatible():
    primary = _partner_cmdr("Primary", ["G"])
    good = _partner_cmdr("Other Partner", ["U"])
    collection = [primary, good, _card("Random", ["G"], "Trample.")]
    partner = _auto_select_partner(primary, collection, None, None, None, 0.0)
    assert partner is not None
    assert partner.name == "Other Partner"


def test_auto_select_partner_none_for_non_partner():
    primary = Card(name="Solo", type_line="Legendary Creature — Human", color_identity=["G"])
    other = _partner_cmdr("Other Partner", ["U"])
    assert _auto_select_partner(primary, [primary, other], None, None, None, 0.0) is None


def test_auto_select_partner_respects_color_filter():
    primary = _partner_cmdr("Primary", ["G"])
    blue = _partner_cmdr("Blue Partner", ["U"])
    white = _partner_cmdr("White Partner", ["W"])
    collection = [primary, blue, white]
    # Restrict combined identity to GW — only the white partner keeps union within GW
    partner = _auto_select_partner(primary, collection, None, {"G", "W"}, None, 0.0)
    assert partner is not None
    assert partner.name == "White Partner"
