import { type APIRequestContext, expect, test } from "@playwright/test";
import { desktopOnly, setScheme, shot } from "./helpers";

test.describe.configure({ mode: "serial" });

async function saveDeck(
  request: APIRequestContext,
  params: Record<string, unknown>,
  name: string,
): Promise<number> {
  const build = await request.post("/api/builds", {
    data: { collection: "builtin:expanded", ...params },
  });
  expect(build.ok()).toBeTruthy();
  const { build_id } = await build.json();
  const saved = await request.post("/api/decks", { data: { build_id, name } });
  expect(saved.status()).toBe(201);
  return (await saved.json()).id;
}

test.describe("Decks", () => {
  let atarka = 0;
  let emmara = 0;
  let atarkaName = "";

  // Every viewport project runs this setup against the same server: names are per project.
  test.beforeAll(async ({ request }, info) => {
    const suffix = info.project.name === "desktop" ? "" : ` (${info.project.name})`;
    atarkaName = `E2E Atarka dragons${suffix}`;
    atarka = await saveDeck(
      request,
      { commander: "Atarka, World Render", theme: "dragons" },
      atarkaName,
    );
    emmara = await saveDeck(
      request,
      { commander: "Emmara, Soul of the Accord", budget: 80 },
      `E2E Emmara budget${suffix}`,
    );
  });

  test("library: search, source filter, rename from the row menu", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/decks");
    await expect(page.getByRole("link", { name: /E2E Atarka dragons/ })).toBeVisible();
    await page.getByRole("textbox", { name: "Search decks" }).fill("emmara");
    await expect(page).toHaveURL(/q=emmara/);
    await expect(page.getByRole("link", { name: /E2E Atarka dragons/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /E2E Emmara budget/ })).toBeVisible();

    await page.getByRole("button", { name: "Actions for E2E Emmara budget" }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    await page.getByRole("dialog").getByRole("textbox", { name: "Name" }).fill("E2E Emmara cheap");
    await page.getByRole("dialog").getByRole("button", { name: "Rename" }).click();
    await expect(page.getByRole("link", { name: /E2E Emmara cheap/ })).toBeVisible();

    await page.getByRole("textbox", { name: "Search decks" }).fill("");
    await page.locator("label", { hasText: /^CLI$/ }).click();
    await expect(page.getByText("No decks match")).toBeVisible();
  });

  test("deck page: tabs, legality, notes, export download", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto(`/decks/${atarka}`);
    await expect(page.getByRole("heading", { name: "E2E Atarka dragons", level: 2 })).toBeVisible();
    await expect(page.getByText("Legal", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Legality" }).click();
    await expect(page.getByText("This deck is legal")).toBeVisible();
    await page.getByRole("tab", { name: "Build info" }).click();
    await expect(page.getByText("dragon", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Notes" }).click();
    await page.getByRole("textbox", { name: "Notes" }).fill("Needs more haste.");
    await page.getByRole("button", { name: "Save notes" }).click();
    await expect(page.getByText("Notes saved")).toBeVisible();
    await page.reload();
    await page.getByRole("tab", { name: "Notes" }).click();
    await expect(page.getByRole("textbox", { name: "Notes" })).toHaveValue("Needs more haste.");

    await page.getByRole("button", { name: "Export" }).click();
    const download = page.waitForEvent("download");
    await page.getByRole("menuitem", { name: "Moxfield" }).last().click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/-moxfield\.txt$/);
  });

  test("rebuild with the saved settings reproduces the deck", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto(`/decks/${atarka}`);
    await page.getByRole("tab", { name: "Build info" }).click();
    await page.getByRole("link", { name: "Rebuild with these settings" }).click();
    await expect(page).toHaveURL(/\/build\?.*run=1/);
    await expect(
      page.getByRole("heading", { name: "Atarka, World Render", level: 2 }),
    ).toBeVisible();
    await expect(page.getByText("Theme: dragon")).toBeVisible();
  });

  test("compare two decks", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/decks");
    await page.getByRole("checkbox", { name: /Select E2E Atarka dragons/ }).check();
    await page.getByRole("checkbox", { name: /Select E2E Emmara cheap/ }).check();
    await page.getByRole("button", { name: "Compare" }).click();
    await expect(page).toHaveURL(/\/decks\/compare\?a=\d+&b=\d+/);
    await expect(page.getByRole("heading", { name: /Only in A/ })).toBeVisible();
    await expect(page.getByRole("table", { name: "Cards in both decks" })).toContainText(
      "Sol Ring",
    );
  });

  test("import a Moxfield list, then delete it", async ({ page, request }, info) => {
    desktopOnly(info);
    const list = await (await request.get(`/api/decks/${emmara}/export?format=moxfield`)).text();
    await page.goto("/decks");
    await page.getByRole("button", { name: "Import" }).click();
    const dialog = page.getByRole("dialog", { name: "Import a deck" });
    await dialog.getByRole("textbox", { name: "Deck" }).fill(list);
    await dialog.getByRole("textbox", { name: "Name (optional)" }).fill("E2E imported");
    await dialog.getByRole("button", { name: "Import" }).click();
    await expect(page).toHaveURL(/\/decks\/\d+$/);
    await expect(page.getByRole("heading", { name: "E2E imported", level: 2 })).toBeVisible();
    await expect(page.getByText("Imported", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Deck actions" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(page).toHaveURL(/\/decks$/);
    await expect(page.getByRole("link", { name: /E2E imported/ })).toHaveCount(0);
  });

  for (const scheme of ["dark", "light"] as const) {
    test(`screenshots (${scheme})`, async ({ page }, info) => {
      await setScheme(page, scheme);
      await page.goto("/decks");
      await expect(page.locator(`a[href="/decks/${atarka}"]`)).toBeVisible();
      await shot(page, info, "decks", scheme);
      await page.goto(`/decks/${atarka}`);
      await expect(page.getByRole("heading", { name: atarkaName, level: 2 })).toBeVisible();
      await shot(page, info, "deck-detail", scheme);
      if (scheme === "dark") {
        await page.goto(`/decks/compare?a=${atarka}&b=${emmara}`);
        await expect(page.getByRole("heading", { name: /Only in A/ })).toBeVisible();
        await shot(page, info, "compare", scheme);
      }
    });
  }
});
