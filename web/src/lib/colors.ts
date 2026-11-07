// Magic color helpers. "C" stands for colorless in pickers and filters.

export const WUBRG = ["W", "U", "B", "R", "G"] as const;
export type ManaColor = (typeof WUBRG)[number];

export const COLOR_NAMES: Record<string, string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
  C: "Colorless",
};

/** Chart colors per mana color (readable in both themes). */
export const COLOR_SWATCH: Record<string, string> = {
  W: "yellow.3",
  U: "blue.6",
  B: "dark.3",
  R: "red.6",
  G: "green.6",
  C: "gray.5",
};

/** WUBRG-ordered letters, e.g. ["G","U"] → "UG"; colorless → "C". */
export function identityString(colors: readonly string[]): string {
  const letters = WUBRG.filter((c) => colors.includes(c)).join("");
  return letters || "C";
}

/** Add or remove a color, keeping WUBRG order with colorless ("C") last. */
export function toggleColor(selected: readonly string[], color: string): string[] {
  const next = selected.includes(color)
    ? selected.filter((c) => c !== color)
    : [...selected, color];
  return [...WUBRG, "C"].filter((c) => next.includes(c));
}
