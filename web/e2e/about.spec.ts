import { expect, test } from "@playwright/test";
import { shot } from "./helpers";

test("about page shows the system status", async ({ page }, info) => {
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: "About CommanderAI", level: 2 })).toBeVisible();
  await expect(page.getByText("500 cards")).toBeVisible();
  await expect(page.getByText("Offline", { exact: true }).last()).toBeVisible();
  await shot(page, info, "about");
});

test("unknown pages show a not-found message", async ({ page }) => {
  await page.goto("/nope");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
