// Renders Scryfall mana-cost strings ("{2}{W/U}{B/P}") with the Mana icon font.

const SYMBOL_RE = /\{([^}]+)\}/g;

/** Map one Scryfall symbol body ("W", "2", "W/U", "B/P", "T") to a mana-font class. */
export function symbolClass(symbol: string): string {
  const s = symbol.toLowerCase().replace(/\//g, "");
  if (s === "t") return "ms-tap";
  if (s === "q") return "ms-untap";
  if (s === "∞") return "ms-infinity";
  return `ms-${s}`;
}

export function parseManaCost(cost: string): string[] {
  return Array.from(cost.matchAll(SYMBOL_RE), (m) => m[1] ?? "");
}

interface ManaCostProps {
  cost: string;
  size?: "sm" | "md" | "lg";
}

const SIZES = { sm: "0.9em", md: "1.1em", lg: "1.4em" } as const;

export function ManaCost({ cost, size = "md" }: ManaCostProps) {
  // Double-faced cards: "{3}{G} // {1}{U}" — render each face, separated.
  const faces = cost.split(" // ");
  return (
    <span
      role="img"
      aria-label={`Mana cost ${cost || "none"}`}
      style={{ fontSize: SIZES[size], whiteSpace: "nowrap" }}
    >
      {faces.map((face, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: faces are positional and never reorder
        <span key={i}>
          {i > 0 && <span style={{ opacity: 0.6 }}>{" // "}</span>}
          {parseManaCost(face).map((symbol, j) => (
            <i
              // biome-ignore lint/suspicious/noArrayIndexKey: symbols repeat ({B}{B}) and never reorder
              key={j}
              className={`ms ms-cost ms-shadow ${symbolClass(symbol)}`}
              style={{ marginInlineEnd: 2 }}
              aria-hidden="true"
            />
          ))}
        </span>
      ))}
    </span>
  );
}

const IDENTITY_ORDER = ["W", "U", "B", "R", "G"];

/** Color identity as mana pips in WUBRG order (colorless → {C}). */
export function ColorIdentity({
  colors,
  size = "md",
}: {
  colors: string[];
  size?: ManaCostProps["size"];
}) {
  const sorted = IDENTITY_ORDER.filter((c) => colors.includes(c));
  const cost = sorted.length ? sorted.map((c) => `{${c}}`).join("") : "{C}";
  return <ManaCost cost={cost} size={size} />;
}
