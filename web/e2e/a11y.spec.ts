import { expect, test } from "@playwright/test";
import { expectAccessible, setScheme } from "./helpers";

// WCAG 2.1 A/AA automated checks (axe-core) on every screen, in both themes.
const PAGES: {
  name: string;
  path: string;
  ready: (p: import("@playwright/test").Page) => Promise<void>;
}[] = [
  {
    name: "collection",
    path: "/collection",
    ready: async (p) => expect(p.getByText(/^Showing \d+ of \d+ cards$/)).toBeVisible(),
  },
  {
    name: "commanders",
    path: "/commanders",
    ready: async (p) => expect(p.getByText("16 commanders")).toBeVisible(),
  },
  {
    name: "build result",
    path: "/build?collection=builtin%3Aexpanded&commander=Zaxara%2C+the+Exemplary&budget=150&bracket=2&run=1",
    ready: async (p) =>
      expect(p.getByRole("heading", { name: "Zaxara, the Exemplary", level: 2 })).toBeVisible(),
  },
  {
    name: "decks",
    path: "/decks",
    ready: async (p) => expect(p.getByRole("heading", { name: "Decks", level: 2 })).toBeVisible(),
  },
  {
    name: "about",
    path: "/about",
    ready: async (p) => expect(p.getByText("291 cards")).toBeVisible(),
  },
];

for (const scheme of ["dark", "light"] as const) {
  for (const page of PAGES) {
    test(`${page.name} has no WCAG A/AA violations (${scheme})`, async ({ page: p }, info) => {
      test.skip(info.project.name === "tablet", "desktop + phone are enough for axe");
      await setScheme(p, scheme);
      await p.goto(page.path);
      await page.ready(p);
      await expectAccessible(p);
    });
  }

  test(`card detail dialog has no violations (${scheme})`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "desktop");
    await setScheme(page, scheme);
    await page.goto("/collection?q=invasion");
    await page.getByRole("button", { name: /^Invasion of Zendikar/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expectAccessible(page);
  });

  test(`deck page and its tabs have no violations (${scheme})`, async ({ page, request }, info) => {
    test.skip(info.project.name !== "desktop", "desktop");
    const build = await (
      await request.post("/api/builds", {
        data: { collection: "builtin:expanded", commander: "Fixture Chaos Commander" },
      })
    ).json();
    const deck = await (
      await request.post("/api/decks", {
        data: { build_id: build.build_id, name: `A11y ${scheme}` },
      })
    ).json();
    await setScheme(page, scheme);
    await page.goto(`/decks/${deck.id}`);
    await expect(page.getByRole("heading", { name: `A11y ${scheme}`, level: 2 })).toBeVisible();
    await expectAccessible(page);
    for (const tab of ["Stats", "Legality", "Build info"]) {
      await page.getByRole("tab", { name: tab }).click();
      await expectAccessible(page);
    }
  });
}
