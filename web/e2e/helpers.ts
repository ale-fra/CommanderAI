import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";

export const isDesktop = (info: TestInfo) => info.project.name === "desktop";

/** Functional flows run once (desktop); layout checks run on every viewport. */
export function desktopOnly(info: TestInfo) {
  if (!isDesktop(info)) info.skip(true, "functional flow — covered on desktop");
}

export async function setScheme(page: Page, scheme: "dark" | "light") {
  await page.addInitScript((s) => localStorage.setItem("mantine-color-scheme-value", s), scheme);
}

export async function useCollection(page: Page, id: string) {
  await page.addInitScript((c) => localStorage.setItem("commanderai.collection", c), id);
}

/** Wait until every visible <img> has loaded (screenshots without gray boxes). */
export async function imagesLoaded(page: Page) {
  await page.waitForFunction(() =>
    Array.from(document.images)
      .filter(
        (img) =>
          (img.getBoundingClientRect().top < window.innerHeight && img.loading !== "lazy") ||
          img.complete,
      )
      .every((img) => img.complete && img.naturalWidth > 0),
  );
  // `decoding="async"` images can be loaded but not yet painted: decode them, then wait two frames.
  await page.evaluate(async () => {
    const visible = Array.from(document.images).filter((img) => {
      const r = img.getBoundingClientRect();
      return r.width > 0 && r.bottom > 0 && r.top < window.innerHeight;
    });
    await Promise.all(visible.map((img) => img.decode().catch(() => undefined)));
    await document.fonts.ready;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
}

export async function shot(page: Page, info: TestInfo, name: string, scheme = "dark") {
  await imagesLoaded(page);
  await page.screenshot({
    path: `e2e/screenshots/${name}-${info.project.name}-${scheme}.png`,
    fullPage: false,
  });
}

/** axe-core WCAG 2.1 A/AA scan of the current page. */
export async function expectAccessible(page: Page, exclude: string[] = []) {
  let builder = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]);
  for (const selector of exclude) builder = builder.exclude(selector);
  const { violations } = await builder.analyze();
  const summary = violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s): ${v.nodes
        .slice(0, 3)
        .map((n) => n.target.join(" "))
        .join(" | ")}`,
  );
  expect(summary, summary.join("\n")).toEqual([]);
}
