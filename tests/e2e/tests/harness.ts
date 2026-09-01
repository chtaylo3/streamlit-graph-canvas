import { test as base, expect, type Page } from "@playwright/test";

type FailureLog = { browserFailures: string[] };

export const test = base.extend<FailureLog>({
  browserFailures: [
    async ({ page }, use, testInfo) => {
      const specializedSet = process.env.SGC_CONTRIB_SET;
      if (
        specializedSet
        && [
          "javascript-stale",
          "javascript-conflict",
          "javascript-adversarial",
          "multi-canvas",
        ].includes(specializedSet)
        && !testInfo.title.includes(`@${specializedSet}`)
      ) {
        testInfo.skip(true, `specialized ${specializedSet} fixture lane`);
      }
      const failures: string[] = [];
      installFailureSentinel(page, failures);
      await use(failures);
      if (failures.length) {
        await testInfo.attach("browser-failures", {
          body: failures.join("\n"),
          contentType: "text/plain",
        });
      }
      expect(failures, "Chromium emitted browser, console, or network failures").toEqual([]);
    },
    { auto: true },
  ],
});

function installFailureSentinel(page: Page, failures: string[]) {
  page.on("pageerror", error => failures.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    const expectedCleanup = process.env.SGC_CONTRIB_SET === "javascript-adversarial"
      && message.text().includes("SGC_JAVASCRIPT_CLEANUP_ERROR")
      && message.text().includes("SGC_JAVASCRIPT_CLEANUP_FIXTURE");
    const expectedFrameBlock = process.env.SGC_CSP_PROXY === "true"
      && message.text().includes("frame-ancestors");
    const expectedCspProbe = process.env.SGC_CSP_PROXY === "true"
      && message.text().includes("https://example.invalid/sgc-csp-probe");
    if (
      message.type() === "error"
      && !expectedCleanup
      && !expectedFrameBlock
      && !expectedCspProbe
    ) {
      failures.push(`console: ${message.text()}`);
    }
  });
  page.on("requestfailed", request => {
    if (request.url() === "https://example.invalid/sgc-csp-probe") return;
    const expectedFrameBlock = process.env.SGC_CSP_PROXY === "true"
      && request.isNavigationRequest()
      && request.frame().parentFrame() !== null
      && new URL(page.url()).hostname === "localhost"
      && new URL(request.url()).hostname === "127.0.0.1";
    if (expectedFrameBlock) return;
    failures.push(`requestfailed: ${request.url()} ${request.failure()?.errorText ?? ""}`);
  });
  page.on("response", response => {
    if (response.status() >= 400) failures.push(`http ${response.status()}: ${response.url()}`);
  });
  page.on("request", request => {
    if (request.url() === "https://example.invalid/sgc-csp-probe") return;
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname) && !["blob:", "data:"].includes(url.protocol)) {
      failures.push(`unexpected external request: ${request.url()}`);
    }
  });
}

export async function openGallery(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Graph Canvas Conformance" })).toBeVisible({
    timeout: 20_000,
  });
  await waitForGalleryStable(page);
  await expect(page.getByRole("button", { name: "service API v1" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole("button", { name: "service Worker" })).toBeVisible({
    timeout: 20_000,
  });
  await waitForGalleryStable(page);
  await expect(page.getByRole("button", { name: "service API v1" })).toBeVisible({
    timeout: 20_000,
  });
}

export async function waitForGalleryStable(page: Page, expectedCanvases = 1) {
  const ready = page.locator('[data-sgc-status="ready"]');
  await expect(ready).toHaveCount(expectedCanvases, { timeout: 20_000 });
  let previousSignature = "";
  let unchangedSince = Date.now();
  await expect.poll(async () => {
    const signature = await ready.evaluateAll((elements) => {
      type IdentityWindow = Window & {
        __sgcElementIds?: WeakMap<Element, number>;
        __sgcNextElementId?: number;
      };
      const root = window as IdentityWindow;
      root.__sgcElementIds ??= new WeakMap();
      root.__sgcNextElementId ??= 1;
      return elements.map((element) => {
        let id = root.__sgcElementIds!.get(element);
        if (id === undefined) {
          id = root.__sgcNextElementId!++;
          root.__sgcElementIds!.set(element, id);
        }
        return `${id}:${element.getAttribute("data-sgc-render-generation") ?? "none"}`;
      }).join(",");
    });
    if (signature !== previousSignature) {
      previousSignature = signature;
      unchangedSince = Date.now();
      return false;
    }
    return Date.now() - unchangedSince >= 2_000;
  }, { timeout: 20_000 }).toBe(true);
}

export { expect };
