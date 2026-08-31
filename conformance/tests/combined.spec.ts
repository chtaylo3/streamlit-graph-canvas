import { test, expect, openGallery } from "./harness";

test("core and selected contrib render without Chromium failures", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await expect(page.getByRole("button", { name: "service API v1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "service Worker" })).toBeVisible();
  if (process.env.SGC_CONTRIB_SET !== "core-only") {
    await expect(page.locator('[data-sgc-badge="count"]')).toHaveCount(2);
    await expect(page.locator('[data-sgc-badge="count"] text').first()).toHaveText("7");
  }
});

test("selection and actions survive a real Streamlit rerun", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await page.locator('.react-flow__node[data-id="api"]').click();
  await expect(page.getByTestId("selected-nodes")).toContainText("api");
  await page.getByRole("button", { name: "Change presentation" }).click();
  await expect(page.getByRole("button", { name: "service API v2" })).toBeVisible();
});

test("topology changes add authoritative nodes", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await page.getByRole("button", { name: "Change topology" }).click();
  await expect(page.getByRole("button", { name: "service Cache" })).toBeVisible();
});

test("nodes support keyboard activation", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  const worker = page.getByRole("button", { name: "service Worker" });
  await worker.focus();
  await worker.press("Enter");
  await expect(page.getByTestId("selected-nodes")).toContainText("worker");
});

test("canvas produces a non-empty Chromium screenshot", async ({ page, browserFailures }, testInfo) => {
  void browserFailures;
  await openGallery(page);
  const canvas = page.locator('[data-sgc-status="ready"]');
  const bounds = await canvas.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.width).toBeGreaterThan(500);
  expect(bounds!.height).toBeGreaterThan(400);
  const screenshot = await canvas.screenshot({ animations: "disabled" });
  expect(screenshot.byteLength).toBeGreaterThan(10_000);
  await testInfo.attach("combined-canvas", {
    body: screenshot,
    contentType: "image/png",
  });
});
