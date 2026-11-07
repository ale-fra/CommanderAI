import anthropic

from commanderai.config import ANTHROPIC_API_KEY, LLM_MODEL
from commanderai.models import Card

_SYSTEM_PROMPT = """You are an expert Magic: The Gathering Commander deck analyst.
Given a commander and its 99 cards, provide a clear, educational explanation of how the deck works.
Write for someone who owns these cards but is new to Commander deckbuilding.
Use plain language. Be specific about card interactions."""


def _build_prompt(commander: Card, cards: list[Card]) -> str:
    lines = []
    lines.append(f"## Commander")
    lines.append(f"**{commander.name}**")
    lines.append(f"Type: {commander.type_line}")
    lines.append(f"Cost: {commander.mana_cost}")
    lines.append(f"Text: {commander.oracle_text}")
    lines.append("")
    lines.append(f"## Deck ({len(cards)} cards)")
    lines.append("")

    for card in sorted(cards, key=lambda c: c.cmc):
        lines.append(f"- {card.name} {card.mana_cost} — {card.type_line}")

    lines.append("")
    lines.append("## Please explain:")
    lines.append("1. **Game Plan** — What is this deck trying to do? How does it win?")
    lines.append("2. **Key Synergies** — What are the 3-5 most important card combos/interactions?")
    lines.append("3. **Early Game** — What should I prioritize in turns 1-4?")
    lines.append("4. **Mid/Late Game** — How does the deck close out?")
    lines.append("5. **Cards to Protect** — Which cards are must-keep and worth protecting?")
    lines.append("6. **Weaknesses** — What beats this deck? What to watch out for?")

    return "\n".join(lines)


def explain_deck(commander: Card, cards: list[Card]) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it to use the explain command."
        )

    prompt = _build_prompt(commander, cards)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
