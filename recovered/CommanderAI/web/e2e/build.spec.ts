import { expect, type Page, test } from "@playwright/test";
import { desktopOnly, setScheme, shot } from "./helpers";

async function pickCommander(page: Page, name: string) {
  const box = page.getByRole("combobox", { name: "Commander" });
  await box.click();
  await box.fill(name.slice(0, 6));
  await page.getByRole("option", { name }).click();
}

/** Card names in the Cards tab, in display order. */
async function deckCards(page: Page): Promise<string[]> {
  return page.getByRole("tabpanel").getByRole("button").allTextContents();
}

test.describe("Build", () => {
  test("choose a commander, build, browse the tabs, rebuild the same deck, save", async ({
    page,
  }, info) => {
    desktopOnly(info);
    await page.goto("/build");
    await expect(page.getByText("No deck yet")).toBeVisible();
    await pickCommander(page, "Zaxara, the Exemplary");
    await page.getByRole("button", { name: "Build deck" }).click();
    await expect(
      page.getByRole("heading", { name: "Zaxara, the Exemplary", level: 2 }),
    ).toBeVisible();
    await expect(page.getByText("40 lands")).toHaveCount(0);
    await expect(page.getByText("37 lands")).toBeVisible();
    await expect(page).toHaveURL(/commander=Zaxara/);

    const before = await deckCards(page);
    expect(before.length).toBeGreaterThan(60);
    await expect(page.getByRole("region", { name: "Ramp (10)" })).toBeVisible();

    await page.getByRole("tab", { name: "Stats" }).click();
    await expect(page.getByText("Mana curve (nonland cards)")).toBeVisible();
    await expect(page.getByText("Roles vs targets")).toBeVisible();
    await page.getByRole("tab", { name: /Tokens/ }).click();
    await expect(page.getByText("Food", { exact: true }).first()).toBeVisible();
    await page.getByRole("tab", { name: "Build log" }).click();
    await expect(page.getByText("Matched 500 cards")).toBeVisible();

    await page.getByRole("tab", { name: "Cards" }).click();
    await page.getByRole("button", { name: "Rebuild" }).click();
    await expect(page.getByRole("button", { name: "Rebuild" })).toBeEnabled();
    expect(await deckCards(page)).toEqual(before);

    await page.getByRole("button", { name: "Save" }).click();
    const dialog = page.getByRole("dialog", { name: "Save deck" });
    await dialog.getByRole("textbox", { name: "Name" }).fill("E2E Zaxara");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(page).toHaveURL(/\/decks\/\d+$/);
    await expect(page.getByRole("heading", { name: "E2E Zaxara", level: 2 })).toBeVisible();
  });

  test("re-roll gives a different, reproducible seed", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/build?commander=Kardur%2C+Doomscourge");
    await page.getByRole("button", { name: "Build deck" }).click();
    await expect(
      page.getByRole("heading", { name: "Kardur, Doomscourge", level: 2 }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Re-roll" }).click();
    const seedBadge = page.getByText(/^Seed \d+$/);
    await expect(seedBadge).toBeVisible();
    const seed = ((await seedBadge.textContent()) ?? "").replace("Seed ", "");
    await expect(page).toHaveURL(new RegExp(`seed=${seed}`));
    const cards = await deckCards(page);
    await page.reload();
    await page.getByRole("button", { name: "Build deck" }).click();
    await expect(page.getByText(`Seed ${seed}`)).toBeVisible();
    expect(await deckCards(page)).toEqual(cards);
  });

  test("auto-pick a commander for a theme", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/build");
    await page.locator("label", { hasText: /^Auto-pick$/ }).click();
    await expect(page.getByRole("button", { name: "Build deck" })).toHaveAttribute(
      "data-disabled",
      "true",
    );
    await expect(page.getByText(/Pick a theme and\/or colors/)).toBeVisible();
    const theme = page.getByRole("combobox", { name: "Theme" });
    await theme.click();
    await theme.fill("dragon");
    await page.getByRole("option", { name: "Dragon", exact: true }).click();
    await page.getByRole("button", { name: "Build deck" }).click();
    await expect(page.getByText("Auto-picked")).toBeVisible();
    await expect(page.getByText("Theme: dragon")).toBeVisible();
  });

  test("budget and bracket are reported, with the offline warning", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/build?commander=Zaxara%2C+the+Exemplary&budget=120&bracket=2");
    await page.getByRole("button", { name: "Build deck" }).click();
    await expect(page.getByText("Bracket 2 (offline rules)")).toBeVisible();
    await expect(page.getByText(/^Budget \$[\d.]+ \/ \$120\.00$/)).toBeVisible();
    const headsUp = page.getByRole("alert").filter({ hasText: "Heads-up" });
    await expect(headsUp).toContainText("combos not checked");
    await expect(headsUp).toContainText("Rhystic Study — game changer");
  });

  test("a build that can't work shows a friendly error", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/build?commander=Gargos%2C+Vicious+Watcher&budget=1");
    await page.getByRole("button", { name: "Build deck" }).click();
    const alert = page.getByRole("alert").filter({ hasText: "Not enough cards" });
    await expect(alert).toContainText("Try a commander with more colors");
  });

  test("links with run=1 build immediately", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto(
      "/build?collection=builtin%3Aexpanded&commander=Atarka%2C+World+Render&seed=3&run=1",
    );
    await expect(
      page.getByRole("heading", { name: "Atarka, World Render", level: 2 }),
    ).toBeVisible();
    await expect(page.getByText("Seed 3")).toBeVisible();
  });

  test("on phones the options collapse after a build", async ({ page }, info) => {
    test.skip(info.project.name !== "phone", "phone layout");
    await page.goto("/build?commander=Zaxara%2C+the+Exemplary");
    await page.getByRole("button", { name: "Build deck" }).click();
    const heading = page.getByRole("heading", { name: "Zaxara, the Exemplary", level: 2 });
    await expect(heading).toBeInViewport();
    await expect(page.getByRole("combobox", { name: "Commander" })).toBeHidden();
    await page.getByRole("button", { name: "Change options" }).click();
    await expect(page.getByRole("combobox", { name: "Commander" })).toBeVisible();
  });

  for (const scheme of ["dark", "light"] as const) {
    test(`screenshot (${scheme})`, async ({ page }, info) => {
      await setScheme(page, scheme);
      await page.goto(
        "/build?collection=builtin%3Aexpanded&commander=Zaxara%2C+the+Exemplary&theme=counters&run=1",
      );
      await expect(
        page.getByRole("heading", { name: "Zaxara, the Exemplary", level: 2 }),
      ).toBeVisible();
      await shot(page, info, "build", scheme);
      if (scheme === "dark") {
        await page.getByRole("tab", { name: "Stats" }).click();
        await expect(page.getByText("Mana curve (nonland cards)")).toBeVisible();
        await page.getByText("Mana curve (nonland cards)").scrollIntoViewIfNeeded();
        await shot(page, info, "build-stats", scheme);
      }
    });
  }
});
