// Client-side filtering / sorting of collection cards, and its URL encoding.
import type { CardSummary } from "../api/types";
import { WUBRG } from "./colors";

export type ColorMode = "within" | "exactly" | "including";
export type SortKey = "name" | "cmc" | "price" | "edhrec" | "quantity";
export type SortDir = "asc" | "desc";

export interface CardFilters {
  q: string;
  colors: string[]; // WUBRG letters and/or "C" (colorless)
  colorMode: ColorMode;
  types: string[];
  cmc: [number, number] | null;
  rarities: string[];
  roles: string[];
  maxPrice: number | null;
  commandersOnly: boolean;
  sort: SortKey;
  dir: SortDir;
}

export const CARD_TYPES = [
  "Creature",
  "Instant",
  "Sorcery",
  "Artifact",
  "Enchantment",
  "Planeswalker",
  "Land",
  "Battle",
] as const;
export const RARITIES = ["common", "uncommon", "rare", "mythic"] as const;
export const ROLES = ["RAMP", "DRAW", "REMOVAL", "WIPE", "THREAT", "UTILITY", "LAND"] as const;
export const CMC_MAX = 10; // slider upper bound = "10 or more"

export const DEFAULT_FILTERS: CardFilters = {
  q: "",
  colors: [],
  colorMode: "within",
  types: [],
  cmc: null,
  rarities: [],
  roles: [],
  maxPrice: null,
  commandersOnly: false,
  sort: "name",
  dir: "asc",
};

export function matchesColors(
  identity: readonly string[],
  selected: string[],
  mode: ColorMode,
): boolean {
  if (selected.length === 0) return true;
  const letters = new Set(selected.filter((c) => c !== "C"));
  const id = new Set(identity);
  switch (mode) {
    case "within":
      return [...id].every((c) => letters.has(c));
    case "exactly":
      return id.size === letters.size && [...letters].every((c) => id.has(c));
    case "including":
      return letters.size === 0 ? id.size === 0 : [...letters].every((c) => id.has(c));
  }
}

function matchesText(card: CardSummary, q: string): boolean {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = `${card.name}\n${card.type_line}\n${card.oracle_text}`.toLowerCase();
  return words.every((w) => haystack.includes(w));
}

export function matchesFilters(card: CardSummary, f: CardFilters): boolean {
  if (!matchesText(card, f.q)) return false;
  if (!matchesColors(card.color_identity, f.colors, f.colorMode)) return false;
  if (f.types.length && !f.types.some((t) => card.type_line.includes(t))) return false;
  if (f.cmc) {
    const [lo, hi] = f.cmc;
    if (card.cmc < lo || (hi < CMC_MAX && card.cmc > hi)) return false;
  }
  if (f.rarities.length && !f.rarities.includes(card.rarity)) return false;
  if (f.roles.length && !f.roles.includes(card.role)) return false;
  if (f.maxPrice !== null && (card.price_usd ?? 0) > f.maxPrice) return false;
  if (f.commandersOnly && !card.is_commander) return false;
  return true;
}

type WithQuantity = CardSummary & { quantity?: number };

function sortValue(card: WithQuantity, key: SortKey): number | string {
  switch (key) {
    case "name":
      return card.name.toLowerCase();
    case "cmc":
      return card.cmc;
    case "price":
      return card.price_usd ?? -1;
    case "edhrec":
      return card.edhrec_rank ?? Number.MAX_SAFE_INTEGER;
    case "quantity":
      return card.quantity ?? 0;
  }
}

export function sortCards<T extends WithQuantity>(cards: T[], key: SortKey, dir: SortDir): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...cards].sort((a, b) => {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
    if (va < vb) return -sign;
    if (va > vb) return sign;
    return a.name.localeCompare(b.name);
  });
}

export function applyFilters<T extends WithQuantity>(cards: T[], f: CardFilters): T[] {
  return sortCards(
    cards.filter((c) => matchesFilters(c, f)),
    f.sort,
    f.dir,
  );
}

export function activeFilterCount(f: CardFilters): number {
  return [
    f.colors.length > 0,
    f.types.length > 0,
    f.cmc !== null,
    f.rarities.length > 0,
    f.roles.length > 0,
    f.maxPrice !== null,
    f.commandersOnly,
  ].filter(Boolean).length;
}

// --- URL encoding (short keys; defaults omitted) -------------------------------------

const list = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);

export function filtersFromParams(p: URLSearchParams): CardFilters {
  const cmc = p.get("cmc")?.split("-").map(Number);
  const price = p.get("price");
  const mode = p.get("cm");
  const sort = p.get("sort");
  return {
    q: p.get("q") ?? "",
    colors: (p.get("c") ?? "").split("").filter((c) => [...WUBRG, "C"].includes(c as never)),
    colorMode: mode === "exactly" || mode === "including" ? mode : "within",
    types: list(p.get("t")),
    cmc:
      cmc && cmc.length === 2 && cmc.every(Number.isFinite)
        ? [cmc[0] ?? 0, cmc[1] ?? CMC_MAX]
        : null,
    rarities: list(p.get("r")),
    roles: list(p.get("role")),
    maxPrice:
      price !== null && price !== "" && Number.isFinite(Number(price)) ? Number(price) : null,
    commandersOnly: p.get("cmd") === "1",
    sort:
      (["name", "cmc", "price", "edhrec", "quantity"] as const).find((k) => k === sort) ?? "name",
    dir: p.get("dir") === "desc" ? "desc" : "asc",
  };
}

export function filtersToParams(f: CardFilters, base?: URLSearchParams): URLSearchParams {
  const p = new URLSearchParams(base);
  const set = (key: string, value: string | null) => (value ? p.set(key, value) : p.delete(key));
  set("q", f.q.trim() || null);
  set("c", f.colors.join("") || null);
  set("cm", f.colors.length && f.colorMode !== "within" ? f.colorMode : null);
  set("t", f.types.join(",") || null);
  set("cmc", f.cmc ? `${f.cmc[0]}-${f.cmc[1]}` : null);
  set("r", f.rarities.join(",") || null);
  set("role", f.roles.join(",") || null);
  set("price", f.maxPrice !== null ? String(f.maxPrice) : null);
  set("cmd", f.commandersOnly ? "1" : null);
  set("sort", f.sort !== "name" ? f.sort : null);
  set("dir", f.dir !== "asc" ? f.dir : null);
  return p;
}
