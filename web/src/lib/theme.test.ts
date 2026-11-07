import { darken } from "../theme";

/** WCAG relative luminance contrast ratio of two #rrggbb colors. */
function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => {
      const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (bl ?? 0);
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

describe("theme contrast", () => {
  it("darken mixes toward black", () => {
    expect(darken("#ffffff", 0.5)).toBe("#808080");
    expect(darken("#e67700", 0)).toBe("#e67700");
  });
  it("light-variant text meets 4.5:1 on the palest light backgrounds", () => {
    // yellow.9 / orange.9 / green.9 / teal.9 darkened, on their shade-0/1 backgrounds
    expect(contrast(darken("#e67700", 0.35), "#fff3bf")).toBeGreaterThan(4.5);
    expect(contrast(darken("#d9480f", 0.35), "#ffe8cc")).toBeGreaterThan(4.5);
    expect(contrast(darken("#2b8a3e", 0.35), "#d3f9d8")).toBeGreaterThan(4.5);
    expect(contrast(darken("#087f5b", 0.35), "#c3fae8")).toBeGreaterThan(4.5);
  });
  it("dimmed text meets 4.5:1 in both schemes", () => {
    expect(contrast("#5c636a", "#ffffff")).toBeGreaterThan(4.5);
    expect(contrast("#a3a3a3", "#242424")).toBeGreaterThan(4.5);
    expect(contrast("#a3a3a3", "#2e2e2e")).toBeGreaterThan(4.5);
  });
});
