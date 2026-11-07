import { ApiError } from "../api/client";
import type { CardSummary, DeckView } from "../api/types";
import { identityString, toggleColor } from "./colors";
import { compareDecks } from "./compare";
import { friendlyError } from "./errors";
import { deckToText } from "./exportDeck";
import { formatDate, formatPrice, plural } from "./format";

const c = (name: string) => ({ name }) as CardSummary;

const deckA: DeckView = {
  commander: c("Alpha"),
  partner: null,
  cards: [
    { card: c("Sol Ring"), slot: "RAMP", reason: "" },
    { card: c("Opt"), slot: "DRAW", reason: "" },
    { card: c("Island"), slot: "LAND", reason: "" },
    { card: c("Island"), slot: "LAND", reason: "" },
  ],
};
const deckB: DeckView = {
  commander: c("Beta"),
  partner: c("Gamma"),
  cards: [
    { card: c("Sol Ring"), slot: "RAMP", reason: "" },
    { card: c("Counterspell"), slot: "REMOVAL", reason: "" },
    { card: c("Island"), slot: "LAND", reason: "" },
  ],
};

describe("exports", () => {
  it("renders Moxfield, Archidekt and MTGO lists", () => {
    expect(deckToText(deckB, "moxfield").split("\n").slice(0, 3)).toEqual([
      "1 Beta *CMDR*",
      "1 Gamma *CMDR*",
      "1 Sol Ring",
    ]);
    expect(deckToText(deckA, "archidekt").split("\n").slice(0, 2)).toEqual([
      "1 Alpha [Commander]",
      "1 Sol Ring [Ramp]",
    ]);
    expect(deckToText(deckA, "mtgo").split("\n")).toHaveLength(5);
  });
});

describe("compare", () => {
  it("splits cards into only-A, only-B and shared with copy counts", () => {
    const diff = compareDecks(deckA, deckB);
    expect(diff.onlyA.map((r) => r.name)).toEqual(["Opt"]);
    expect(diff.onlyB.map((r) => r.name)).toEqual(["Counterspell"]);
    expect(diff.shared).toEqual([
      { name: "Island", slot: "LAND", a: 2, b: 1 },
      { name: "Sol Ring", slot: "RAMP", a: 1, b: 1 },
    ]);
    expect(diff.commandersB).toEqual(["Beta", "Gamma"]);
  });
});

describe("formatting", () => {
  it("formats prices, dates, plurals and identities", () => {
    expect(formatPrice(1.5)).toBe("$1.50");
    expect(formatPrice(null)).toBe("—");
    expect(formatDate("2026-11-05T10:00:43+00:00")).toBe("2026-11-05 10:00");
    expect(plural(1, "card")).toBe("1 card");
    expect(plural(3, "card")).toBe("3 cards");
    expect(identityString(["G", "U"])).toBe("UG");
    expect(identityString([])).toBe("C");
  });
});

describe("toggleColor", () => {
  it("adds in WUBRG order and removes", () => {
    expect(toggleColor(["G"], "U")).toEqual(["U", "G"]);
    expect(toggleColor(["U", "G"], "U")).toEqual(["G"]);
    expect(toggleColor(["R"], "C")).toEqual(["R", "C"]);
  });
});

describe("friendly errors", () => {
  it("adds a title and a hint for known codes", () => {
    const err = new ApiError(422, {
      code: "collection_too_small",
      message: "Collection too small (12 cards).",
      details: [],
      data: {},
    });
    expect(friendlyError(err)).toEqual({
      title: "Collection too small",
      message: "Collection too small (12 cards). Pick a larger collection in the header.",
      details: [],
    });
    expect(friendlyError(new Error("boom")).title).toBe("Something went wrong");
  });
});
