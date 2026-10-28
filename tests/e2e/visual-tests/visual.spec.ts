import type { Page } from "@playwright/test";
import { test, expect, waitForGalleryStable } from "../tests/harness";

// Font rasterization differs by OS, so baselines exist only for the pinned
// Playwright Linux image. Regenerate them with update_visual_baselines.py.
test.skip(process.platform !== "linux", "visual baselines are Linux-only");

const canvas = (page: Page) => page.locator('[data-sgc-status="ready"]');

async function open(page: Page, scene: string) {
  await page.goto(`/?scene=${scene}`);
  await expect(page.getByRole("heading", { name: "Visual Gallery" })).toBeVisible({
    timeout: 20_000,
  });
  await waitForGalleryStable(page);
  // Keep hover styles out of the frame.
  await page.mouse.move(0, 0);
}

async function openSearch(page: Page, query: string) {
  await page.getByText("Find in this view", { exact: true }).click();
  await page.getByRole("textbox", { name: "Find node names" }).fill(query);
  await expect(page.getByRole("status").filter({ hasText: "matches" })).toBeVisible();
  await page.getByRole("textbox", { name: "Find node names" }).blur();
}

test("default scene", async ({ page }) => {
  await open(page, "default");
  await expect(canvas(page)).toHaveScreenshot("default.png");
});

test("selected node", async ({ page }) => {
  await open(page, "selected");
  await page.getByRole("button", { name: "service Worker", exact: true }).click();
  await waitForGalleryStable(page);
  await page.mouse.move(0, 0);
  await page.getByRole("button", { name: "service Worker", exact: true }).blur();
  await expect(canvas(page)).toHaveScreenshot("selected.png");
});

test("search matches", async ({ page }) => {
  await open(page, "search");
  await openSearch(page, "Worker, Database");
  await expect(canvas(page)).toHaveScreenshot("search.png");
});

test("dark host theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await open(page, "dark");
  await expect(canvas(page)).toHaveScreenshot("dark.png");
});

test("phone-width search panel @mobile", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "phone-width project only");
  await open(page, "mobile-search");
  await openSearch(page, "Worker");
  await expect(canvas(page)).toHaveScreenshot("mobile-search.png");
});
