import { test, expect, openGallery, waitForGalleryStable } from "./harness";
import AxeBuilder from "@axe-core/playwright";

test("core and selected contrib render without Chromium failures", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await expect(page.getByRole("button", { name: "service API v1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "service Worker" })).toBeVisible();
  if (process.env.SGC_CONTRIB_SET !== "core-only") {
    await expect(page.locator('[data-sgc-badge="count-prims"]')).toHaveCount(2);
    await expect(page.locator('[data-sgc-badge="count-prims"] text').first()).toHaveText("7");
    await expect(page.locator('[data-sgc-transport="javascript"] [data-sgc-js-chip="true"]')).toHaveCount(2);
    await expect(page.locator('[data-sgc-transport="atlas"] image').first()).toHaveAttribute("href", /^blob:/);
    if (process.env.SGC_CONTRIB_SET === "transports") {
      await expect(page.locator('[data-sgc-javascript-only-fixture="true"]')).toHaveCount(2);
    }
  }
});

test("selection and actions survive a real Streamlit rerun", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await page.locator('.react-flow__node[data-id="api"]').click();
  await expect(page.getByTestId("selected-nodes")).toContainText("api");
  await expect(page.locator('.react-flow__node[data-id="api"] .sgc-node')).toHaveClass(/selected/);
  await expect(page.getByTestId("action-sequences")).toContainText("1");
  await page.locator(".react-flow__controls-zoomin").click();
  await expect(page.getByTestId("viewport-state")).not.toContainText("none");
  await waitForGalleryStable(page);
  const viewport = await page.getByTestId("viewport-state").textContent();
  await page.getByRole("button", { name: "Change presentation" }).click();
  await expect(page.getByRole("button", { name: "service API v2" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator('.react-flow__node[data-id="api"] .sgc-node')).toHaveClass(/selected/);
  await expect(page.getByTestId("selected-nodes")).toContainText("api");
  await expect(page.getByTestId("action-sequences")).toContainText("1");
  await expect(page.getByTestId("viewport-state")).toHaveText(viewport ?? "");
});

test("topology changes add authoritative nodes", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await page.getByRole("button", { name: "Change topology" }).click();
  await expect(page.getByRole("button", { name: "service Cache" })).toBeVisible({
    timeout: 20_000,
  });
});

test("React Flow geometry, handles, and zoom limits remain compatible", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  const api = page.locator('.react-flow__node[data-id="api"]');
  const worker = page.locator('.react-flow__node[data-id="worker"]');
  await expect(api).toBeVisible({ timeout: 20_000 });
  await expect(worker).toBeVisible({ timeout: 20_000 });
  await expect.poll(async () => {
    const [apiBox, workerBox] = await Promise.all([
      api.evaluate((element) => {
        const { width, y } = element.getBoundingClientRect();
        return { width, y };
      }),
      worker.evaluate((element) => {
        const { y } = element.getBoundingClientRect();
        return { y };
      }),
    ]);
    return apiBox.width > 150 && workerBox.y > apiBox.y;
  }).toBe(true);
  await expect(api.locator('[data-nodeid="api"][data-handleid="out"]')).toHaveCount(2);
  const zoomIn = page.locator(".react-flow__controls-zoomin");
  for (let index = 0; index < 20 && await zoomIn.isEnabled(); index += 1) {
    await zoomIn.click();
  }
  await expect(zoomIn).toBeDisabled();
  const transform = await page.locator(".react-flow__viewport").getAttribute("style");
  expect(transform).toMatch(/scale\(2\.5\)/);
});

test("rerenders do not duplicate React Flow action handlers", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await page.getByRole("button", { name: "Change presentation" }).click();
  await expect(page.getByRole("button", { name: "service API v2" })).toBeVisible();
  await waitForGalleryStable(page);
  await page.getByRole("button", { name: "service API v2" }).click();
  await expect(page.getByTestId("action-sequences")).toHaveText("1");
});

test("component styles remain contained to the canvas host", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  await expect(page.getByRole("heading", { name: "Graph Canvas Conformance" })).not.toHaveCSS("font-family", /monospace/i);
  await expect(page.locator(".sgc-root")).toHaveCount(1);
});

test("nodes support keyboard activation", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  const worker = page.getByRole("button", { name: "service Worker" });
  await worker.focus();
  await worker.press("Enter");
  await expect(page.getByTestId("selected-nodes")).toContainText("worker");
});

test("nodes support Space keyboard activation", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  const api = page.getByRole("button", { name: "service API v1" });
  await api.focus();
  await expect(api).toHaveCSS("outline-style", "solid");
  await api.press("Space");
  await expect(page.getByTestId("selected-nodes")).toContainText("api");
});

test("styles, named ports, and accessible badge meaning are honored", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  const api = page.locator('.react-flow__node[data-id="api"] .sgc-node');
  await expect(api).toHaveCSS("border-radius", "16px");
  await expect(api).toHaveCSS("border-color", "rgb(37, 99, 235)");
  await expect(page.locator('.react-flow__node[data-id="api"] [data-handleid="out"]')).toHaveCount(2);
  await expect(page.locator('.react-flow__edge[data-id="api-worker"] path.react-flow__edge-path')).toHaveCSS("stroke", "rgb(220, 38, 38)");
  if (process.env.SGC_CONTRIB_SET !== "core-only") {
    await expect(page.getByRole("button", { name: /service API v1, 7/ })).toBeVisible();
  }
});

test("dark palette variants render in Chromium", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET === "core-only", "requires stock badge fixture");
  void browserFailures;
  await page.emulateMedia({ colorScheme: "dark" });
  await openGallery(page);
  await expect(page.locator('[data-sgc-badge="count-prims"] rect').first()).toHaveCSS("fill", "rgb(96, 165, 250)");
});

test("JavaScript and ATLAS run under the documented CSP", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET === "core-only", "requires transport fixture");
  test.skip(process.env.SGC_CSP_PROXY !== "true", "CSP proxy lane only");
  void browserFailures;
  await page.addInitScript(() => {
    (globalThis as typeof globalThis & { __sgcCspViolations: string[] })
      .__sgcCspViolations = [];
    addEventListener("securitypolicyviolation", (event) => {
      (globalThis as typeof globalThis & { __sgcCspViolations: string[] })
        .__sgcCspViolations.push(`${event.violatedDirective}:${event.blockedURI}`);
    });
  });
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain(
    "connect-src 'self' ws://127.0.0.1:8514",
  );
  await expect(page.getByRole("heading", { name: "Graph Canvas Conformance" })).toBeVisible({
    timeout: 20_000,
  });
  await waitForGalleryStable(page);
  await expect(page.locator('[data-sgc-status="ready"]')).toBeVisible();
  await expect(page.locator('[data-sgc-transport="javascript"] [data-sgc-js-chip="true"]').first()).toBeVisible();
  await expect(page.locator('[data-sgc-transport="atlas"] image').first()).toHaveAttribute("href", /^blob:/);
  const violations = await page.evaluate(
    () => (globalThis as typeof globalThis & { __sgcCspViolations: string[] })
      .__sgcCspViolations,
  );
  expect(violations).toEqual([]);
  const externalFetchBlocked = await page.evaluate(async () => {
    try {
      await fetch("https://example.invalid/sgc-csp-probe");
      return false;
    } catch {
      return true;
    }
  });
  expect(externalFetchBlocked).toBe(true);
  await expect.poll(async () => page.evaluate(
    () => (globalThis as typeof globalThis & { __sgcCspViolations: string[] })
      .__sgcCspViolations,
  )).toContainEqual(expect.stringMatching(/^connect-src:https:\/\/example\.invalid/));
});

test("canvas has no serious automated accessibility violations", async ({ page, browserFailures }) => {
  void browserFailures;
  await openGallery(page);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  const componentViolations = results.violations
    .map((violation) => ({
      ...violation,
      nodes: violation.nodes.filter((node) => {
        const target = JSON.stringify(node.target);
        return target.includes("sgc-") || target.includes("react-flow");
      }),
    }))
    .filter((violation) =>
      violation.nodes.length > 0
      && ["serious", "critical"].includes(violation.impact ?? ""),
    );
  expect(componentViolations).toEqual([]);
});

test("hostile installed renderers are isolated", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET !== "hostile", "hostile fixture set only");
  void browserFailures;
  await openGallery(page);
  await expect(page.getByTestId("discovery-diagnostics")).toContainText("SGC_MANIFEST_PARSE");
  await expect(page.getByTestId("ownership-diagnostic")).toHaveText("SGC_RENDERER_MODULE_OWNERSHIP");
  await expect(page.getByRole("button", { name: /service API v1/ })).toBeVisible();
});

test("SR-T2 stale installed JavaScript bootstrap fails before rendering @javascript-stale", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET !== "javascript-stale", "stale fixture set only");
  void browserFailures;
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Graph Canvas Conformance" })).toBeVisible();
  await expect(page.locator('[data-sgc-status="fatal"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("alert")).toContainText("SGC_JAVASCRIPT_REGISTRATION_CONFLICT");
  await expect(page.locator('[data-sgc-badge="javascript-stale"] > *')).toHaveCount(0);
});

test("SR-T3 installed JavaScript conflicts are order-independent @javascript-conflict", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET !== "javascript-conflict", "conflict fixture set only");
  void browserFailures;
  await openGallery(page);
  await expect(page.getByTestId("renderer-enablement-diagnostic")).toHaveText(
    "SGC_RENDERER_KIND_CONFLICT,SGC_RENDERER_KIND_CONFLICT",
  );
});

test("SR-T4 and SR-T5 trusted JavaScript violations are detected and isolated @javascript-adversarial", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET !== "javascript-adversarial", "adversarial fixture set only");
  void browserFailures;
  await openGallery(page);
  await expect(page.locator('[data-sgc-render-error="true"]')).toHaveCount(2);
  await expect(page.locator('[data-sgc-badge="javascript-factory-throw"] > *')).toHaveCount(0);
  await expect(page.locator('[data-sgc-badge="javascript-render-throw"] > *')).toHaveCount(0);
  await expect(page.locator('[data-sgc-adversarial-behavior="healthy"]')).toBeVisible();
  await expect(page.locator('[data-sgc-out-of-scope-mutation="true"]')).toBeAttached();
  await page.getByRole("button", { name: "Change presentation" }).click();
  await expect(page.getByRole("button", { name: "service API v2" })).toBeVisible();
  const leakedCalls = await page.evaluate(() => {
    globalThis.dispatchEvent(new Event("sgc-leak-probe"));
    return (globalThis as typeof globalThis & { __sgcLeakedListenerCalls?: number })
      .__sgcLeakedListenerCalls ?? 0;
  });
  expect(leakedCalls).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: /service API v2/ })).toBeVisible();
});

test("SR-T7 unmounting one canvas does not revoke another canvas URL @multi-canvas", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CONTRIB_SET !== "multi-canvas", "multi-canvas fixture set only");
  void browserFailures;
  await page.goto("/");
  await waitForGalleryStable(page, 2);
  const primaryImage = page.locator('[data-sgc-transport="atlas"] image').first();
  const primaryUrl = await primaryImage.getAttribute("href");
  expect(primaryUrl).toMatch(/^blob:/);
  const mountSecondary = page.getByRole("checkbox", { name: "Mount secondary canvas" });
  await page.locator("label").filter({ has: mountSecondary }).click();
  await expect(mountSecondary).not.toBeChecked();
  await waitForGalleryStable(page);
  await expect(page.locator('[data-sgc-transport="atlas"] image').first()).toHaveAttribute(
    "href",
    primaryUrl!,
    { timeout: 20_000 },
  );
});

test("Pillow forward incompatibility fails closed without raster output @pillow-forward", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_EXPECT_PILLOW_FAILURE !== "true", "Pillow forward lane only");
  void browserFailures;
  await page.goto("/");
  await expect(page.getByTestId("pillow-forward-diagnostic")).toHaveText(
    "SGC_ATLAS_DEPENDENCY_VERSION",
    { timeout: 20_000 },
  );
  await expect(page.locator('[data-sgc-transport="atlas"] image')).toHaveCount(0);
  await expect(page.locator('[data-sgc-status="ready"]')).toHaveCount(0);
});

test("CSP frame-ancestors allows self and blocks a different origin @csp-framing", async ({ page, browserFailures }) => {
  test.skip(process.env.SGC_CSP_PROXY !== "true", "CSP proxy lane only");
  void browserFailures;
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain("frame-ancestors 'self'");
  await page.evaluate(() => {
    const frame = document.createElement("iframe");
    frame.id = "same";
    frame.src = "http://127.0.0.1:8514/";
    document.body.append(frame);
  });
  await expect(page.frameLocator("#same").getByRole("heading", { name: "Graph Canvas Conformance" })).toBeVisible({ timeout: 20_000 });
  await page.goto("http://localhost:8514/__csp_frame_host");
  await page.evaluate(() => {
    const frame = document.createElement("iframe");
    frame.id = "blocked";
    frame.src = "http://127.0.0.1:8514/";
    document.body.append(frame);
  });
  await expect(page.frameLocator("#blocked").getByRole("heading", { name: "Graph Canvas Conformance" })).toHaveCount(0);
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
