import { test, expect, waitForGalleryStable } from "../tests/harness";
import { selectHostTheme } from "../tests/theme-helpers";

test("full-label overlays and focus remain readable after actual host theme changes", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await waitForGalleryStable(page);
  for (const theme of ["Dark", "Light"] as const) {
    await selectHostTheme(page, theme);
    await waitForGalleryStable(page);
    const host = page.locator(".sgc-root");
    const reveal = page
      .getByTestId("rf__node-path")
      .locator(".sgc-label-reveal");
    await reveal.scrollIntoViewIfNeeded();
    await waitForGalleryStable(page);
    await reveal.focus();
    await expect(reveal).toHaveCSS("outline-style", "solid");
    await reveal.click();
    const dialog = page.getByRole("dialog", { name: "Full node label" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveCSS("color-scheme", theme.toLowerCase());
    const colors = await host.evaluate((e) => {
      const probe = document.createElement("span");
      probe.style.color = "var(--st-text-color)";
      probe.style.backgroundColor = "var(--st-background-color)";
      e.appendChild(probe);
      const result = {
        color: getComputedStyle(probe).color,
        background: getComputedStyle(probe).backgroundColor,
      };
      probe.remove();
      return result;
    });
    await expect(dialog).toHaveCSS("color", colors.color);
    await expect(dialog).toHaveCSS("background-color", colors.background);
    await expect(
      page.getByRole("button", { name: "Copy full label", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close", exact: true }).click();
  }
});
