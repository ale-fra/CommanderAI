import {
  type CSSVariablesResolver,
  createTheme,
  Drawer,
  type MantineColorsTuple,
  Modal,
} from "@mantine/core";

// Brand accent: a muted violet. WUBRG colors are reserved for color identity.
const violet: MantineColorsTuple = [
  "#f3f0ff",
  "#e5dbff",
  "#d0bfff",
  "#b197fc",
  "#9775fa",
  "#845ef7",
  "#7950f2",
  "#7048e8",
  "#6741d9",
  "#5f3dc4",
];

export const theme = createTheme({
  primaryColor: "brand",
  colors: { brand: violet },
  fontFamily: "'Inter Variable', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  defaultRadius: "md",
  cursorType: "pointer",
  components: {
    // Close buttons are icon-only: give them an accessible name everywhere.
    Modal: Modal.extend({ defaultProps: { closeButtonProps: { "aria-label": "Close dialog" } } }),
    Drawer: Drawer.extend({ defaultProps: { closeButtonProps: { "aria-label": "Close panel" } } }),
  },
});

/** Mix a #rrggbb color with black (amount 0–1). */
export function darken(hex: string, amount: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const channel = (shift: number) => Math.round(((n >> shift) & 255) * (1 - amount));
  return `#${[16, 8, 0].map((s) => channel(s).toString(16).padStart(2, "0")).join("")}`;
}

// WCAG AA (4.5:1) for secondary text and light-variant badges/alerts in both schemes.
// Mantine's defaults measure 4.03:1 (dimmed text, dark), 3.3:1 (dimmed text, light)
// and as low as 2.2:1 (yellow/orange light variants, light scheme).
export const cssVariablesResolver: CSSVariablesResolver = (t) => ({
  variables: {},
  light: {
    "--mantine-color-dimmed": "#5c636a",
    ...Object.fromEntries(
      Object.entries(t.colors).map(([name, shades]) => [
        `--mantine-color-${name}-light-color`,
        darken(shades[9], 0.35),
      ]),
    ),
  },
  dark: {
    "--mantine-color-dimmed": "#a3a3a3",
  },
});
