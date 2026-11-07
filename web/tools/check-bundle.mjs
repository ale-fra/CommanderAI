// Performance budget: the JavaScript and CSS loaded before any page renders
// (entry chunk + its static imports) must stay under the budgets below (gzip).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const BUDGET_JS_KB = 300;
const BUDGET_CSS_KB = 80;
const dist = new URL("../dist/", import.meta.url).pathname;
const html = readFileSync(join(dist, "index.html"), "utf8");

const refs = (pattern) => [...html.matchAll(pattern)].map((m) => m[1]);
const js = refs(/<script[^>]+src="\/([^"]+\.js)"/g).concat(
  refs(/<link[^>]+rel="modulepreload"[^>]+href="\/([^"]+)"/g),
);
const css = refs(/<link[^>]+rel="stylesheet"[^>]+href="\/([^"]+)"/g);
const gz = (files) =>
  files.reduce((sum, f) => sum + gzipSync(readFileSync(join(dist, f))).length, 0) / 1024;

const jsKb = gz([...new Set(js)]);
const cssKb = gz([...new Set(css)]);
console.log(
  `initial JS  ${jsKb.toFixed(1)} kB gzip (budget ${BUDGET_JS_KB} kB) — ${js.length} file(s)`,
);
console.log(
  `initial CSS ${cssKb.toFixed(1)} kB gzip (budget ${BUDGET_CSS_KB} kB) — ${css.length} file(s)`,
);
if (jsKb > BUDGET_JS_KB || cssKb > BUDGET_CSS_KB) {
  console.error("Bundle budget exceeded");
  process.exit(1);
}
console.log("Bundle within budget");
