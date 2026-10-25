import { test, expect, openGallery, waitForGalleryStable } from "./harness";
import { imagePixel, selectHostTheme } from "./theme-helpers";

for (const os of ["light", "dark"] as const) {
  test(`actual host theme selection overrides ${os} OS for palette and images`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: os });
    await openGallery(page);
    for (const selected of ["Dark", "Light", "System"] as const) {
      await selectHostTheme(page, selected);
      const theme = selected === "System" ? os : selected.toLowerCase();
      const dark = theme === "dark";
      const host = page.locator(".sgc-root");
      await expect(host).toHaveCSS("color-scheme", theme);
      await expect(host.locator(".react-flow")).toHaveCSS(
        "color-scheme",
        theme,
      );
      await expect(host.locator(".sgc-node").first()).toHaveCSS(
        "background-color",
        dark ? "rgb(15, 23, 42)" : "rgb(248, 250, 252)",
      );
      await expect(host.locator(".react-flow__edge-path").first()).toHaveCSS(
        "stroke",
        dark ? "rgb(248, 113, 113)" : "rgb(220, 38, 38)",
      );
      const themeColors = await host.evaluate((e) => {
        const probe = document.createElement("span");
        probe.style.color = "var(--st-text-color)";
        probe.style.background = "var(--st-background-color)";
        e.appendChild(probe);
        const values = {
          text: getComputedStyle(probe).color,
          background: getComputedStyle(probe).backgroundColor,
        };
        probe.remove();
        return values;
      });
      const edgeLabel = host.locator('.react-flow__edge[data-id="api-worker"]');
      await expect(edgeLabel.locator(".react-flow__edge-text")).toHaveText(
        "Calls",
      );
      await expect(edgeLabel.locator(".react-flow__edge-text")).toHaveCSS(
        "fill",
        themeColors.text,
      );
      await expect(edgeLabel.locator(".react-flow__edge-textbg")).toHaveCSS(
        "fill",
        themeColors.background,
      );
      if (process.env.SGC_CONTRIB_SET !== "core-only") {
        await expect(
          host.locator('[data-sgc-badge="count-prims"] rect').first(),
        ).toHaveCSS("fill", dark ? "rgb(96, 165, 250)" : "rgb(37, 99, 235)");
        const sprite = host.locator(
          '.react-flow__node[data-id="api"] [data-sgc-transport="sprite"]',
        );
        const atlas = host.locator(
          '.react-flow__node[data-id="api"] [data-sgc-transport="atlas"]',
        );
        await expect
          .poll(async () => {
            const pixel = await imagePixel(sprite);
            return dark ? pixel[2] > pixel[0] : pixel[0] > pixel[2];
          })
          .toBe(true);
        await expect
          .poll(async () => (await imagePixel(atlas))[0])
          .toBeCloseTo(dark ? 96 : 37, 0);
      }
      await waitForGalleryStable(page);
      const viewport = await page.getByTestId("viewport-state").textContent();
      await page.getByRole("button", { name: "Change presentation" }).click();
      await waitForGalleryStable(page);
      await expect(page.getByTestId("viewport-state")).toHaveText(
        viewport ?? "",
      );
      await expect(host).toHaveCSS("color-scheme", theme);
    }
  });
}

test("application CSS wins over a later upstream layer without escaping the shadow root", async ({
  page,
}) => {
  await openGallery(page);
  await page.locator(".sgc-root").evaluate((host) => {
    const style = document.createElement("style");
    style.textContent =
      "@layer xyflow { .sgc-root .react-flow .sgc-node:focus-visible { outline: 0; } .sgc-root .react-flow { color-scheme: dark; } }";
    host.getRootNode().appendChild(style);
  });
  const node = page.locator(".sgc-node").first();
  await node.focus();
  await expect(node).toHaveCSS("outline-width", "3px");
  await expect(page.locator(".react-flow")).toHaveCSS(
    "color-scheme",
    await page
      .locator(".sgc-root")
      .evaluate((e) => getComputedStyle(e).colorScheme),
  );
  await page.addStyleTag({
    content: "svg, .react-flow, .sgc-node { visibility: hidden; }",
  });
  await expect(node).toBeVisible();
  await expect(page.locator(".react-flow__controls-zoomin")).toBeVisible();
});
