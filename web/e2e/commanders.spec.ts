import { expect, test } from "@playwright/test";
import { desktopOnly, setScheme, shot } from "./helpers";

test.describe("Commanders", () => {
  test("gallery of owned commanders with color filter and sorting", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/commanders");
    await expect(page.getByText("16 commanders")).toBeVisible();
    const builds = page.getByRole("link", { name: /^Build with / });
    await expect(builds.first()).toHaveAccessibleName("Build with Syr Konrad, the Grim");

    await page
      .getByRole("group", { name: "Commander colors" })
      .getByRole("button", { name: "Blue" })
      .click();
    await expect(page).toHaveURL(/c=U/);
    await expect(page.getByText("1 commander")).toBeVisible(); // mono-blue: Tekuthal
    await page.locator("label", { hasText: /^Support$/ }).click();
    await expect(page).toHaveURL(/sort=support/);
  });

  test("suggest a commander for a theme, then build with it", async ({ page }, info) => {
    desktopOnly(info);
    await page.goto("/commanders");
    await page.getByRole("button", { name: "Suggest a commander" }).click();
    await page.getByRole("combobox", { name: "Theme" }).click();
    await page.getByRole("combobox", { name: "Theme" }).fill("tokens");
    await page.getByRole("option", { name: "Tokens", exact: true }).click();
    await page.getByRole("button", { name: "Suggest", exact: true }).click();
    const table = page.getByRole("table", { name: "Suggested commanders" });
    await expect(table.getByRole("row").nth(1)).toContainText("Zaxara, the Exemplary");
    await table.getByRole("link", { name: "Build with Zaxara, the Exemplary" }).click();
    await expect(page).toHaveURL(/\/build\?.*commander=Zaxara.*theme=tokens/);
  });

  for (const scheme of ["dark", "light"] as const) {
    test(`screenshot (${scheme})`, async ({ page }, info) => {
      await setScheme(page, scheme);
      await page.goto("/commanders");
      await expect(page.getByText("16 commanders")).toBeVisible();
      await shot(page, info, "commanders", scheme);
    });
  }
});
