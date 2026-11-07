import { expect, test } from "@playwright/test";
import { desktopOnly, setScheme, shot, useCollection } from "./helpers";

test.describe("Collection", () => {
  test("shows the active collection with images and counts", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/collection$/);
    await expect(page.getByRole("heading", { name: "Expanded sample", level: 2 })).toBeVisible();
    await expect(page.getByText("500 cards (796 copies)")).toBeVisible();
    await expect(page.getByText("Showing 500 of 500 cards")).toBeVisible();
    const first = page.getByRole("button", { name: /show details/ }).first();
    await expect(first.locator("img")).toHaveJSProperty("naturalWidth", 488);
  });

  test("search, filters and sorting narrow the list and live in the URL", async ({
    page,
  }, info) => {
    desktopOnly(info);
    await page.goto("/collection");
    await page.getByRole("textbox", { name: "Search cards" }).fill("dragon");
    await expect(page).toHaveURL(/q=dragon/);
    const count = page.getByText(/^Showing \d+ of 500 cards$/);
    await expect(count).not.toHaveText("Showing 500 of 500 cards");

    await page.getByRole("textbox", { name: "Search cards" }).fill("");
    await page.getByRole("button", { name: "Blue" }).click();
    await page.getByRole("button", { name: "Green" }).click();
    await expect(page).toHaveURL(/c=UG/);
    await page.locator("label", { hasText: /^Exactly$/ }).click();
    await expect(page).toHaveURL(/cm=exactly/);
    const commandersOnly = page.getByRole("switch", { name: "Commanders only" });
    await commandersOnly.click();
    await expect(commandersOnly).toBeChecked();
    await expect(page.getByText("Showing 4 of 500 cards")).toBeVisible(); // Tatyova, Inga and Esika, Ezuri, Zegana

    await page.getByRole("combobox", { name: "Sort by" }).click();
    await page.getByRole("option", { name: "EDHREC rank" }).click();
    const names = page.getByRole("button", { name: /show details/ });
    await expect(names.first()).toHaveAccessibleName(/^Tatyova, Benthic Druid/);

    // Deep link restores everything.
    await page.reload();
    await expect(page.getByText("Showing 4 of 500 cards")).toBeVisible();
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(page.getByText("Showing 500 of 500 cards")).toBeVisible();
  });

  test("list view and the card detail dialog (double-faced card flips)", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/collection?view=list&q=invasion");
    await page.getByRole("button", { name: "Invasion of Zendikar // Awakened Skyclave" }).click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Awakened Skyclave", exact: true }),
    ).toBeVisible();
    await expect(dialog.getByText("Owned")).toBeVisible();
    await dialog.getByRole("button", { name: "Show back" }).click();
    await expect(dialog.getByRole("img", { name: /back face/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("a commander's detail offers to build with it", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/collection?q=zaxara");
    await page.getByRole("button", { name: /^Zaxara, the Exemplary/ }).click();
    await page.getByRole("button", { name: "Build with this commander" }).click();
    await expect(page).toHaveURL(/\/build\?commander=Zaxara/);
  });

  test("switching the active collection (header) reloads the cards", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/collection");
    await page.getByRole("combobox", { name: "Active collection" }).click();
    await page.getByRole("option", { name: /Precon: First Flight/ }).click();
    await expect(
      page.getByRole("heading", { name: "Precon: First Flight", level: 2 }),
    ).toBeVisible();
    await expect(page.getByText("Showing 72 of 72 cards")).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Precon: First Flight", level: 2 }),
    ).toBeVisible();
  });

  test("upload → check → save → rename → delete a collection", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/collection");
    await page.getByRole("button", { name: "Upload" }).click();
    const dialog = page.getByRole("dialog", { name: "Upload a collection" });
    await dialog.getByRole("textbox", { name: "Name" }).fill("E2E upload");
    await dialog
      .getByRole("textbox", { name: "Cards" })
      .fill("1 Sol Ring\n1 Arcane Signat\n1 Not A Real Card\n1 Zaxara, the Exemplary\n30 Forest\n");
    await expect(dialog.getByRole("button", { name: "Save collection" })).toBeDisabled();
    await dialog.getByRole("button", { name: "Check cards" }).click();
    const preview = dialog.getByTestId("upload-preview");
    await expect(preview.getByText("1 name(s) corrected")).toBeVisible();
    await expect(preview.getByText("Arcane Signat → Arcane Signet")).toBeVisible();
    await expect(preview.getByText("Not A Real Card")).toBeVisible();
    await dialog.getByRole("button", { name: "Save collection" }).click();
    await expect(page.getByRole("heading", { name: "E2E upload", level: 2 })).toBeVisible();
    await expect(page.getByText("Some lines didn't match the card catalog")).toBeVisible();

    await page.getByRole("button", { name: "Manage this collection" }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    await page.getByRole("dialog").getByRole("textbox", { name: "Name" }).fill("E2E renamed");
    await page.getByRole("dialog").getByRole("button", { name: "Rename" }).click();
    await expect(page.getByRole("heading", { name: "E2E renamed", level: 2 })).toBeVisible();

    await page.getByRole("button", { name: "Manage this collection" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    // Falls back to the default collection.
    await expect(page.getByRole("heading", { name: "Expanded sample", level: 2 })).toBeVisible();
  });

  test("filters open in a drawer on small screens", async ({ page }, info) => {
    test.skip(info.project.name !== "phone", "phone layout");
    await page.goto("/collection");
    await page.getByRole("button", { name: "Filters" }).click();
    const drawer = page.getByRole("dialog", { name: "Filters" });
    await drawer.getByRole("button", { name: "Red" }).click();
    await drawer.getByRole("button", { name: /^Show \d+ cards$/ }).click();
    await expect(page).toHaveURL(/c=R/);
  });

  for (const scheme of ["dark", "light"] as const) {
    test(`screenshot (${scheme})`, async ({ page }, info) => {
      await setScheme(page, scheme);
      await useCollection(page, "builtin:expanded");
      await page.goto("/collection");
      await expect(page.getByText("Showing 500 of 500 cards")).toBeVisible();
      await shot(page, info, "collection", scheme);
      if (scheme === "dark") {
        await page.getByRole("textbox", { name: "Search cards" }).fill("zaxara");
        await page.getByRole("button", { name: /^Zaxara, the Exemplary/ }).click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await shot(page, info, "card-detail", scheme);
      }
    });
  }
});
