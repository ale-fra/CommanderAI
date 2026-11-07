from commanderai.models import Card


class CardIndex:
    def __init__(self, cards: list[Card], non_legal_names: set[str] | None = None):
        self.all_cards = cards
        self.by_name: dict[str, Card] = {}
        self.by_name_lower: dict[str, Card] = {}
        self.non_legal_names: set[str] = non_legal_names or set()

        for card in cards:
            self.by_name[card.name] = card
            self.by_name_lower[card.name.lower()] = card
            if card.card_faces:
                for face in card.card_faces:
                    face_name = face.get("name", "")
                    if face_name and face_name != card.name:
                        self.by_name[face_name] = card
                        self.by_name_lower[face_name.lower()] = card

    def get(self, name: str) -> Card | None:
        return self.by_name.get(name) or self.by_name_lower.get(name.lower())

    def find_commanders(self, color_filter: set[str] | None = None) -> list[Card]:
        commanders = []
        for card in self.all_cards:
            if not _is_valid_commander(card):
                continue
            if color_filter and not set(card.color_identity).issubset(color_filter):
                continue
            commanders.append(card)
        return commanders

    def filter_by_color_identity(self, identity: list[str]) -> list[Card]:
        identity_set = set(identity)
        return [c for c in self.all_cards if set(c.color_identity).issubset(identity_set)]


def _is_valid_commander(card: Card) -> bool:
    type_line = card.type_line.lower()
    if "legendary" in type_line and "creature" in type_line:
        return True
    if "legendary" in type_line and "planeswalker" in type_line:
        oracle = (card.oracle_text or "").lower()
        if "can be your commander" in oracle:
            return True
    oracle = (card.oracle_text or "").lower()
    if "can be your commander" in oracle:
        return True
    return False
