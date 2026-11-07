"""Partner / second-commander support.

Commander allows a few ways to have *two* cards in the command zone:

- **Partner** — any two cards that both have plain Partner.
- **Partner with X** — pairs only with the named card.
- **Partner — <group>** (restricted) — pairs only within the named group.
- **Friends forever** — any two cards with Friends forever.
- **Choose a Background** + a **Background** enchantment.
- **Doctor's companion** + a **Time Lord Doctor**.

This module detects a card's partner ability and decides whether two cards may
legally share a command zone, plus merges two commanders into one view for
color identity / synergy scoring.
"""

import re
from dataclasses import dataclass, field

from commanderai.models import Card

_PARTNER_WITH_RE = re.compile(r"partner with ([^(\n.]+?)(?:\s*\(| and | or |\.|\n|$)", re.IGNORECASE)
_PARTNER_GROUP_RE = re.compile(r"partner\s*[—-]\s*([^(\n]+?)(?:\s*\(|\n|$)", re.IGNORECASE)


@dataclass
class PartnerAbility:
    plain: bool = False
    partner_with: list[str] = field(default_factory=list)
    group: str | None = None
    background_chooser: bool = False
    is_background: bool = False
    friends_forever: bool = False
    doctors_companion: bool = False
    is_doctor: bool = False

    @property
    def has_any(self) -> bool:
        return (
            self.plain
            or bool(self.partner_with)
            or self.group is not None
            or self.background_chooser
            or self.is_background
            or self.friends_forever
            or self.doctors_companion
            or self.is_doctor
        )

    @property
    def can_take_partner(self) -> bool:
        """True if this card actively wants a second commander."""
        return (
            self.plain
            or bool(self.partner_with)
            or self.group is not None
            or self.background_chooser
            or self.friends_forever
            or self.doctors_companion
        )


def partner_ability(card: Card) -> PartnerAbility:
    keywords = {k.lower() for k in card.keywords}
    text = (card.oracle_text or "").lower()
    type_line = (card.type_line or "").lower()

    ability = PartnerAbility()
    ability.is_background = "background" in type_line
    ability.is_doctor = "time lord" in type_line and "doctor" in type_line
    ability.background_chooser = "choose a background" in keywords or "choose a background" in text
    ability.doctors_companion = "doctor's companion" in keywords or "doctor's companion" in text
    ability.friends_forever = "friends forever" in text or "friends forever" in keywords

    # Restricted "Partner — Group"
    group_match = _PARTNER_GROUP_RE.search(card.oracle_text or "")
    if group_match:
        ability.group = group_match.group(1).strip().lower()

    if "partner with" in keywords or "partner with" in text:
        for m in _PARTNER_WITH_RE.finditer(card.oracle_text or ""):
            name = m.group(1).strip()
            if name:
                ability.partner_with.append(name)
    elif ("partner" in keywords or re.search(r"\bpartner\b", text)) and ability.group is None:
        ability.plain = True

    return ability


def can_partner(a: Card, b: Card) -> bool:
    """Whether cards ``a`` and ``b`` may legally be paired in the command zone."""
    if a.name == b.name:
        return False
    pa = partner_ability(a)
    pb = partner_ability(b)

    # Partner with X (name match either direction)
    if any(_names_match(n, b.name) for n in pa.partner_with):
        return True
    if any(_names_match(n, a.name) for n in pb.partner_with):
        return True

    # Choose a Background + Background
    if (pa.background_chooser and pb.is_background) or (pb.background_chooser and pa.is_background):
        return True

    # Doctor's companion + Time Lord Doctor
    if (pa.doctors_companion and pb.is_doctor) or (pb.doctors_companion and pa.is_doctor):
        return True

    # Friends forever
    if pa.friends_forever and pb.friends_forever:
        return True

    # Restricted partner group
    if pa.group and pb.group and pa.group == pb.group:
        return True

    # Plain partner
    if pa.plain and pb.plain:
        return True

    return False


def _names_match(partner_name: str, card_name: str) -> bool:
    pn = partner_name.strip().lower()
    cn = card_name.strip().lower()
    # Handle "Partner with X" referencing the front face of a card.
    return pn == cn or cn.split("//")[0].strip() == pn or cn.startswith(pn)


def merge_commanders(a: Card, b: Card) -> Card:
    """Combine two commanders into one view for identity/synergy scoring.

    The merged card is only used internally (color identity union, concatenated
    oracle text, union of keywords); its mana cost/type are not meaningful.
    """
    return Card(
        name=f"{a.name} + {b.name}",
        oracle_text=f"{a.oracle_text}\n{b.oracle_text}",
        color_identity=sorted(set(a.color_identity) | set(b.color_identity)),
        keywords=sorted({*a.keywords, *b.keywords}),
        type_line=a.type_line,
    )


def combined_identity(commander: Card, partner: Card | None) -> set[str]:
    identity = set(commander.color_identity)
    if partner:
        identity |= set(partner.color_identity)
    return identity
