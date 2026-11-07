// Card-level difference between two decks (commanders compared separately).
import type { DeckSlot, DeckView } from "../api/types";

export interface CompareRow {
  name: string;
  slot: DeckSlot;
  a: number; // copies in deck A
  b: number; // copies in deck B
}

export interface DeckComparison {
  onlyA: CompareRow[];
  onlyB: CompareRow[];
  shared: CompareRow[];
  commandersA: string[];
  commandersB: string[];
}

function counts(deck: DeckView): Map<string, { n: number; slot: DeckSlot }> {
  const m = new Map<string, { n: number; slot: DeckSlot }>();
  for (const pick of deck.cards) {
    const cur = m.get(pick.card.name);
    m.set(pick.card.name, { n: (cur?.n ?? 0) + 1, slot: cur?.slot ?? pick.slot });
  }
  return m;
}

export function compareDecks(a: DeckView, b: DeckView): DeckComparison {
  const ca = counts(a);
  const cb = counts(b);
  const names = [...new Set([...ca.keys(), ...cb.keys()])].sort((x, y) => x.localeCompare(y));
  const result: DeckComparison = {
    onlyA: [],
    onlyB: [],
    shared: [],
    commandersA: [a.commander.name, ...(a.partner ? [a.partner.name] : [])],
    commandersB: [b.commander.name, ...(b.partner ? [b.partner.name] : [])],
  };
  for (const name of names) {
    const x = ca.get(name);
    const y = cb.get(name);
    const row: CompareRow = { name, slot: (x ?? y)?.slot ?? "UTILITY", a: x?.n ?? 0, b: y?.n ?? 0 };
    if (x && y) result.shared.push(row);
    else if (x) result.onlyA.push(row);
    else result.onlyB.push(row);
  }
  return result;
}
