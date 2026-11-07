import { render, screen } from "@testing-library/react";
import { ColorIdentity, ManaCost, parseManaCost, symbolClass } from "./ManaCost";

describe("mana symbols", () => {
  it("parses Scryfall cost strings", () => {
    expect(parseManaCost("{2}{W/U}{B/P}{X}")).toEqual(["2", "W/U", "B/P", "X"]);
    expect(parseManaCost("")).toEqual([]);
  });

  it("maps symbols to mana-font classes", () => {
    expect(symbolClass("W")).toBe("ms-w");
    expect(symbolClass("10")).toBe("ms-10");
    expect(symbolClass("W/U")).toBe("ms-wu");
    expect(symbolClass("U/P")).toBe("ms-up");
    expect(symbolClass("2/W")).toBe("ms-2w");
    expect(symbolClass("T")).toBe("ms-tap");
  });

  it("renders an accessible label and one icon per symbol", () => {
    const { container } = render(<ManaCost cost="{1}{B}{G}{U}" />);
    expect(screen.getByRole("img", { name: "Mana cost {1}{B}{G}{U}" })).toBeInTheDocument();
    expect(container.querySelectorAll("i.ms")).toHaveLength(4);
  });

  it("renders both faces of a double-faced card", () => {
    const { container } = render(<ManaCost cost="{3}{G} // {1}{U}" />);
    expect(container.querySelectorAll("i.ms")).toHaveLength(4);
    expect(container.textContent).toContain("//");
  });

  it("orders color identity WUBRG and shows colorless as {C}", () => {
    const { container, rerender } = render(<ColorIdentity colors={["G", "B", "U"]} />);
    const classes = Array.from(container.querySelectorAll("i.ms"), (i) => i.className);
    expect(classes.map((c) => c.split(" ").pop())).toEqual(["ms-u", "ms-b", "ms-g"]);
    rerender(<ColorIdentity colors={[]} />);
    expect(container.querySelector("i.ms")?.className).toContain("ms-c");
  });
});
