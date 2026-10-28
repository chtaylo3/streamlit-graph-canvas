import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { test, expect, waitForGalleryStable } from "../tests/harness";

const node = (page: Page, label: string) =>
  page.getByRole("button", { name: `service ${label}`, exact: true });
const selected = (page: Page) => page.getByText(/^Selected: /);
const actions = (page: Page) => page.getByText(/^Actions: /);

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Interaction Gallery" })).toBeVisible({
    timeout: 20_000,
  });
  await waitForGalleryStable(page);
}

async function toggle(page: Page, name: string) {
  await page.getByRole("checkbox", { name, exact: true }).press("Space");
  await waitForGalleryStable(page);
}

/** Toggle a control that removes the canvas, then wait for it to unmount. */
async function toggleWithoutCanvas(page: Page, name: string) {
  await page.getByRole("checkbox", { name, exact: true }).press("Space");
  await expect(page.locator("[data-sgc-status=\"ready\"]")).toHaveCount(0, { timeout: 20_000 });
}

async function chooseMode(page: Page, mode: "single" | "multiple" | "none") {
  await page.getByText(mode, { exact: true }).click();
  await waitForGalleryStable(page);
}

test("single selection replaces the selection on each click", async ({ page }) => {
  await open(page);
  await expect(page.locator(".react-flow__minimap")).toBeVisible();
  await node(page, "API").click();
  await expect(selected(page)).toHaveText("Selected: api");
  await node(page, "Worker").click({ modifiers: ["Shift"] });
  await expect(selected(page)).toHaveText("Selected: worker");
});

test("multiple selection toggles nodes and reports modifiers to Python", async ({ page }) => {
  await open(page);
  await chooseMode(page, "multiple");
  await node(page, "API").click();
  await expect(selected(page)).toHaveText("Selected: api");
  await node(page, "Worker").click({ modifiers: ["Shift", "Alt"] });
  await expect(selected(page)).toHaveText("Selected: api,worker");
  await expect(page.getByText(/^Last: /)).toHaveText(
    "Last: worker shift=True meta=False alt=True",
  );
  // Clicking a selected node again removes it.
  await node(page, "API").click();
  await expect(selected(page)).toHaveText("Selected: worker");
  await expect(actions(page)).toHaveText("Actions: 3");
});

test("selection mode none ignores clicks and sends no actions", async ({ page }) => {
  await open(page);
  await chooseMode(page, "none");
  await node(page, "API").click();
  await node(page, "Worker").press("Enter");
  await waitForGalleryStable(page);
  await expect(selected(page)).toHaveText("Selected: -");
  await expect(actions(page)).toHaveText("Actions: 0");
});

test("disabled nodes leave the tab order and ignore keyboard activation", async ({ page }) => {
  await open(page);
  await toggle(page, "Disable worker");
  const worker = node(page, "Worker");
  await expect(worker).toHaveAttribute("aria-disabled", "true");
  await expect(worker).toHaveAttribute("tabindex", "-1");
  await worker.dispatchEvent("keydown", { key: "Enter" });
  await worker.click({ force: true });
  await waitForGalleryStable(page);
  await expect(actions(page)).toHaveText("Actions: 0");
  // Keyboard users can still activate enabled nodes.
  await node(page, "API").press("Enter");
  await expect(selected(page)).toHaveText("Selected: api");
});

test("an invalid graph shows its diagnostic and never mounts a canvas", async ({ page }) => {
  await open(page);
  await toggleWithoutCanvas(page, "Invalid graph");
  const error = page.getByTestId("stException");
  await expect(error).toContainText("SGC_GRAPH_EDGE_ENDPOINT");
  await expect(page.locator("[data-sgc-status]")).toHaveCount(0);
  // Fixing the data recovers without a page reload.
  await page.getByRole("checkbox", { name: "Invalid graph", exact: true }).press("Space");
  await waitForGalleryStable(page);
  await expect(error).toHaveCount(0);
});

test("a graph at the element budget becomes ready within budget", async ({ page }) => {
  await open(page);
  const started = Date.now();
  await page.getByRole("checkbox", { name: "Large graph", exact: true }).press("Space");
  await expect(page.locator('[data-sgc-status="ready"]')).toHaveCount(1);
  await expect(page.locator(".react-flow__node")).toHaveCount(350, { timeout: 30_000 });
  await waitForGalleryStable(page);
  // Generous for CI runners; catches pathological layout regressions.
  expect(Date.now() - started).toBeLessThan(30_000);
  const viewportTransform = page.locator(".react-flow__viewport");
  const before = await viewportTransform.getAttribute("style");
  await page.evaluate(() => {
    const root = window as Window & { __sgcLongTasks?: number[] };
    root.__sgcLongTasks = [];
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) root.__sgcLongTasks!.push(entry.duration);
    }).observe({ type: "longtask" });
  });
  const pane = (await page.locator(".react-flow__pane").boundingBox())!;
  await page.mouse.move(pane.x + pane.width / 2, pane.y + pane.height / 2);
  for (let i = 0; i < 5; i++) await page.mouse.wheel(0, -200);
  await waitForGalleryStable(page);
  const longTasks = await page.evaluate(
    () => (window as Window & { __sgcLongTasks?: number[] }).__sgcLongTasks ?? [],
  );
  // The wheel input must really zoom, or the timing check is vacuous.
  expect(await viewportTransform.getAttribute("style")).not.toBe(before);
  // Zooming a full-budget graph must not freeze the main thread.
  expect(Math.max(0, ...longTasks)).toBeLessThan(1_000);
});

test("telemetry posts OTLP metrics only when an endpoint is configured", async ({ page }) => {
  const payloads: unknown[] = [];
  await page.route("**/sgc-telemetry", async (route) => {
    payloads.push(route.request().postDataJSON());
    await route.fulfill({ status: 204 });
  });
  await open(page);
  // With telemetry enabled, unmounting flushes pending metrics immediately, so
  // an unmount with it disabled is a deterministic point to assert silence.
  await toggleWithoutCanvas(page, "Hide canvas");
  await page.waitForLoadState("networkidle");
  expect(payloads).toEqual([]);
  await toggle(page, "Hide canvas");
  await toggle(page, "Telemetry");
  await node(page, "API").click();
  await toggleWithoutCanvas(page, "Hide canvas");
  await expect.poll(() => payloads.length, { timeout: 15_000 }).toBeGreaterThan(0);
  const body = payloads[0] as {
    resourceMetrics: { scopeMetrics: { metrics: { name: string }[] }[] }[];
  };
  const metrics = body.resourceMetrics[0].scopeMetrics[0].metrics;
  expect(metrics.length).toBeGreaterThan(0);
  expect(metrics.every((metric) => typeof metric.name === "string")).toBe(true);
});

test("open search panel has no serious accessibility violations", async ({ page }) => {
  await open(page);
  await page.getByText("Find in this view", { exact: true }).click();
  await page.getByText("Filter criteria", { exact: true }).click();
  await page.getByRole("button", { name: "Add filter", exact: true }).click();
  await page.getByRole("textbox", { name: "Find node names" }).fill("a");
  // Scope the scan to the panel inside the component's shadow root.
  await page.evaluate(() => {
    const host = [...document.querySelectorAll("*")].find((element) =>
      element.shadowRoot?.querySelector(".sgc-search-panel"),
    );
    host!.setAttribute("data-sgc-axe-host", "");
  });
  const results = await new AxeBuilder({ page })
    .include({ fromShadowDom: ["[data-sgc-axe-host]", ".sgc-search-panel"] })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.passes.length).toBeGreaterThan(0);
  const serious = results.violations.filter((violation) =>
    ["serious", "critical"].includes(violation.impact ?? ""),
  );
  expect(serious).toEqual([]);
});

test("keyboard Tab order reaches every enabled node", async ({ page }) => {
  await open(page);
  await node(page, "API").focus();
  const reached = new Set<string>();
  for (let i = 0; i < 6; i++) {
    const label = await page.evaluate(() => {
      let active = document.activeElement;
      while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
      return active?.getAttribute("aria-label");
    });
    if (label) reached.add(label);
    await page.keyboard.press("Tab");
  }
  expect(reached).toContain("service API");
  expect(reached).toContain("service Worker");
  expect(reached).toContain("store Database");
});

test("canvas renders, fits, and selects by tap at phone width @mobile", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "phone-width project only");
  await open(page);
  const canvas = page.locator('[data-sgc-status="ready"]');
  const frame = await canvas.boundingBox();
  const viewport = page.viewportSize()!;
  expect(frame!.width).toBeLessThanOrEqual(viewport.width);
  // Canvases at most 480px wide drop the minimap so it cannot cover nodes.
  await expect(canvas.locator(".react-flow__minimap")).toBeHidden();
  for (const label of ["API", "Worker"]) {
    const box = await node(page, label).boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(frame!.x - 1);
    expect(box!.x + box!.width).toBeLessThanOrEqual(frame!.x + frame!.width + 1);
  }
  await node(page, "Worker").tap();
  await expect(selected(page)).toHaveText("Selected: worker");
});

test("search panel fits inside a phone-width canvas @mobile", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "phone-width project only");
  await open(page);
  const frame = await page.locator('[data-sgc-status="ready"]').boundingBox();
  await page.getByText("Find in this view", { exact: true }).tap();
  const panel = await page.locator(".sgc-search-panel").boundingBox();
  expect(frame).not.toBeNull();
  expect(panel).not.toBeNull();
  // The panel is sized from the canvas container (cqw), not the page viewport.
  expect(panel!.x).toBeGreaterThanOrEqual(frame!.x - 1);
  expect(panel!.x + panel!.width).toBeLessThanOrEqual(frame!.x + frame!.width + 1);
  await expect(page.getByRole("button", { name: "Clear search" })).toBeInViewport({ ratio: 1 });
});
