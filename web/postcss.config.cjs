// mana-font's stylesheet declares @font-face rules for every font format and for
// "MPlantin" (a typeface not covered by mana-font's licence). Drop them all; the
// Mana icon font is declared in src/styles/fonts.css with woff2/woff only.
const dropManaFontFaces = () => ({
  postcssPlugin: "drop-mana-font-faces",
  AtRule: {
    "font-face": (rule) => {
      const file = rule.source?.input?.file ?? "";
      if (file.includes("mana-font")) rule.remove();
    },
  },
});
dropManaFontFaces.postcss = true;

module.exports = {
  plugins: [
    require("postcss-preset-mantine"),
    require("postcss-simple-vars")({
      variables: {
        "mantine-breakpoint-xs": "36em",
        "mantine-breakpoint-sm": "48em",
        "mantine-breakpoint-md": "62em",
        "mantine-breakpoint-lg": "75em",
        "mantine-breakpoint-xl": "88em",
      },
    }),
    dropManaFontFaces(),
  ],
};
