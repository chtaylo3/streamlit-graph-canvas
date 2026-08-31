import { test as base, expect, type Page } from "@playwright/test";

type FailureLog = { browserFailures: string[] };

export const test = base.extend<FailureLog>({
  browserFailures: [
    async ({ page }, use, testInfo) => {
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
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("requestfailed", request => {
    failures.push(`requestfailed: ${request.url()} ${request.failure()?.errorText ?? ""}`);
  });
  page.on("response", response => {
    if (response.status() >= 400) failures.push(`http ${response.status()}: ${response.url()}`);
  });
  page.on("request", request => {
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname) && !["blob:", "data:"].includes(url.protocol)) {
      failures.push(`unexpected external request: ${request.url()}`);
    }
  });
}

export async function openGallery(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Graph Canvas Conformance" })).toBeVisible();
  await expect(page.locator('[data-sgc-status="ready"]')).toBeVisible();
}

export { expect };
