// Text exports computed in the browser (used for unsaved build previews; saved
// decks use GET /api/decks/{id}/export). Matches the CLI/API formats.
import type { DeckView } from "../api/types";

export type TextFormat = "mtgo" | "moxfield" | "archidekt";

export const TEXT_FORMATS: { value: TextFormat; label: string }[] = [
  { value: "moxfield", label: "Moxfield" },
  { value: "archidekt", label: "Archidekt" },
  { value: "mtgo", label: "MTGO / plain list" },
];

const capitalize = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

export function deckToText(deck: DeckView, format: TextFormat): string {
  const commanders = [deck.commander, ...(deck.partner ? [deck.partner] : [])];
  const lines: string[] = [];
  for (const c of commanders) {
    if (format === "moxfield") lines.push(`1 ${c.name} *CMDR*`);
    else if (format === "archidekt") lines.push(`1 ${c.name} [Commander]`);
    else lines.push(`1 ${c.name}`);
  }
  for (const pick of deck.cards) {
    lines.push(
      format === "archidekt"
        ? `1 ${pick.card.name} [${capitalize(pick.slot)}]`
        : `1 ${pick.card.name}`,
    );
  }
  return lines.join("\n");
}
