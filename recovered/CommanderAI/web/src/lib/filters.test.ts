import type { CardSummary } from "../api/types";
import {
  activeFilterCount,
  applyFilters,
  DEFAULT_FILTERS,
  filtersFromParams,
  filtersToParams,
  matchesColors,
  matchesFilters,
} from "./filters";

function card(partial: Partial<CardSummary> & { name: string }): CardSummary {
  return {
    mana_cost: "",
    cmc: 0,
    type_line: "Instant",
    oracle_text: "",
    colors: [],
    color_identity: [],
    keywords: [],
    power: null,
    toughness: null,
    rarity: "common",
    edhrec_rank: null,
    price_usd: null,
    game_changer: false,
    role: "UTILITY",
    is_commander: false,
    partner_tags: [],
    images: { front: null, back: null },
    ...partial,
  };
}

const solRing = card({
  name: "Sol Ring",
  type_line: "Artifact",
  cmc: 1,
  role: "RAMP",
  edhrec_rank: 1,
});
const zaxara = card({
  name: "Zaxara, the Exemplary",
  type_line: "Legendary Creature — Nightmare Hydra",
  cmc: 4,
  color_identity: ["B", "G", "U"],
  rarity: "mythic",
  price_usd: 0.5,
  is_commander: true,
  oracle_text: "Deathtouch",
});
const opt = card({ name: "Opt", color_identity: ["U"], cmc: 1, role: "DRAW", price_usd: 0.1 });
const bolt = card({
  name: "Lightning Bolt",
  color_identity: ["R"],
  cmc: 1,
  role: "REMOVAL",
  price_usd: 2,
});
const all = [zaxara, bolt, solRing, opt];

describe("color identity modes", () => {
  it("within: identity is a subset (colorless always fits)", () => {
    expect(matchesColors(["U"], ["U", "B"], "within")).toBe(true);
    expect(matchesColors([], ["U"], "within")).toBe(true);
    expect(matchesColors(["U", "R"], ["U"], "within")).toBe(false);
  });
  it("exactly: same set; C alone means colorless only", () => {
    expect(matchesColors(["B", "G", "U"], ["U", "B", "G"], "exactly")).toBe(true);
    expect(matchesColors(["U"], ["U", "B"], "exactly")).toBe(false);
    expect(matchesColors([], ["C"], "exactly")).toBe(true);
    expect(matchesColors(["U"], ["C"], "exactly")).toBe(false);
  });
  it("including: contains every selected color", () => {
    expect(matchesColors(["B", "G", "U"], ["U"], "including")).toBe(true);
    expect(matchesColors(["U"], ["U", "B"], "including")).toBe(false);
    expect(matchesColors([], ["C"], "including")).toBe(true);
  });
  it("no selection matches everything", () => {
    expect(matchesColors(["W"], [], "exactly")).toBe(true);
  });
});

describe("filters", () => {
  it("searches name, type and rules text (all words)", () => {
    const f = { ...DEFAULT_FILTERS, q: "hydra deathtouch" };
    expect(all.filter((c) => matchesFilters(c, f)).map((c) => c.name)).toEqual([
      "Zaxara, the Exemplary",
    ]);
  });
  it("combines type, mana value, rarity, role, price and commander filters", () => {
    expect(
      all.filter((c) => matchesFilters(c, { ...DEFAULT_FILTERS, types: ["Artifact"] })),
    ).toEqual([solRing]);
    expect(all.filter((c) => matchesFilters(c, { ...DEFAULT_FILTERS, cmc: [2, 10] }))).toEqual([
      zaxara,
    ]);
    expect(
      all.filter((c) => matchesFilters(c, { ...DEFAULT_FILTERS, rarities: ["mythic"] })),
    ).toEqual([zaxara]);
    expect(all.filter((c) => matchesFilters(c, { ...DEFAULT_FILTERS, roles: ["DRAW"] }))).toEqual([
      opt,
    ]);
    expect(
      all.filter((c) => matchesFilters(c, { ...DEFAULT_FILTERS, maxPrice: 1 })).map((c) => c.name),
    ).toEqual(["Zaxara, the Exemplary", "Sol Ring", "Opt"]);
    expect(
      all.filter((c) => matchesFilters(c, { ...DEFAULT_FILTERS, commandersOnly: true })),
    ).toEqual([zaxara]);
  });
  it("'10 or more' mana value upper bound is open-ended", () => {
    const big = card({ name: "Big", cmc: 15 });
    expect(matchesFilters(big, { ...DEFAULT_FILTERS, cmc: [5, 10] })).toBe(true);
  });
  it("sorts with name as tie-breaker; unknown prices last when descending", () => {
    expect(applyFilters(all, DEFAULT_FILTERS).map((c) => c.name)).toEqual([
      "Lightning Bolt",
      "Opt",
      "Sol Ring",
      "Zaxara, the Exemplary",
    ]);
    const byPrice = applyFilters(all, { ...DEFAULT_FILTERS, sort: "price", dir: "desc" });
    expect(byPrice.map((c) => c.name)).toEqual([
      "Lightning Bolt",
      "Zaxara, the Exemplary",
      "Opt",
      "Sol Ring",
    ]);
  });
  it("counts active filters (search and sort excluded)", () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
    expect(
      activeFilterCount({ ...DEFAULT_FILTERS, q: "x", colors: ["U"], maxPrice: 3, sort: "cmc" }),
    ).toBe(2);
  });
});

describe("URL round-trip", () => {
  it("encodes only non-defaults and decodes back", () => {
    expect(filtersToParams(DEFAULT_FILTERS).toString()).toBe("");
    const f = {
      ...DEFAULT_FILTERS,
      q: "dragon",
      colors: ["R", "G"],
      colorMode: "exactly" as const,
      types: ["Creature", "Artifact"],
      cmc: [2, 5] as [number, number],
      rarities: ["rare"],
      roles: ["THREAT"],
      maxPrice: 2.5,
      commandersOnly: true,
      sort: "price" as const,
      dir: "desc" as const,
    };
    const params = filtersToParams(f, new URLSearchParams("view=list"));
    expect(params.get("view")).toBe("list");
    expect(filtersFromParams(params)).toEqual(f);
  });
  it("ignores invalid values", () => {
    const f = filtersFromParams(
      new URLSearchParams("c=XYZW&cm=bogus&cmc=a-b&price=cheap&sort=nope"),
    );
    expect(f).toEqual({ ...DEFAULT_FILTERS, colors: ["W"] });
  });
});
