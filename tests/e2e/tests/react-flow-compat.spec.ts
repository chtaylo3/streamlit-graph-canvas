import { test, expect, openGallery, waitForGalleryStable } from "./harness";

for (const osTheme of ["light", "dark"] as const) {
  test(`React Flow chrome follows host theme changes with ${osTheme} OS preference`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: osTheme });
    await openGallery(page);
    const host = page.locator(".sgc-root");
    const flow = host.locator(".react-flow");
    const zoomIn = flow.locator(".react-flow__controls-zoomin");
    const palettes = [
      {
        background: "rgb(250, 250, 250)",
        secondary: "rgb(230, 230, 230)",
        text: "rgb(20, 20, 20)",
        border: "rgb(100, 100, 100)",
      },
      {
        background: "rgb(15, 15, 15)",
        secondary: "rgb(35, 35, 35)",
        text: "rgb(240, 240, 240)",
        border: "rgb(160, 160, 160)",
      },
    ];
    for (const palette of palettes) {
      // Model the host updating its public theme variables after mounting.
      // Both OS/host mismatches and live theme changes use the same assertions.
      await host.evaluate((element, colors) => {
        element.style.setProperty("--st-background-color", colors.background);
        element.style.setProperty(
          "--st-secondary-background-color",
          colors.secondary,
        );
        element.style.setProperty("--st-text-color", colors.text);
        element.style.setProperty("--st-border-color", colors.border);
      }, palette);
      await page.mouse.move(0, 0);
      await expect(flow).toHaveCSS("background-color", palette.background);
      await expect(flow.locator(".react-flow__background")).toHaveCSS(
        "background-color",
        palette.background,
      );
      await expect(zoomIn).toHaveCSS("background-color", palette.background);
      await expect(zoomIn).toHaveCSS("color", palette.text);
      await expect(zoomIn).toHaveCSS("border-bottom-color", palette.border);
      await expect(flow.locator(".react-flow__minimap")).toHaveCSS(
        "background-color",
        palette.background,
      );
      await expect(flow.locator(".react-flow__minimap-node").first()).toHaveCSS(
        "fill",
        palette.border,
      );
      await expect(flow.locator(".react-flow__handle").first()).toHaveCSS(
        "background-color",
        palette.text,
      );
      await expect(flow.locator(".react-flow__handle").first()).toHaveCSS(
        "border-color",
        palette.background,
      );
      await zoomIn.hover();
      await expect(zoomIn).toHaveCSS("background-color", palette.secondary);
      await expect(zoomIn).toHaveCSS("color", palette.text);
    }
  });
}

test("selecting a node preserves supported edge stacking", async ({ page }) => {
  await openGallery(page);
  const edge = page.locator('.react-flow__edge[data-id="api-worker"]');
  const layer = () =>
    edge.evaluate(
      (element) => getComputedStyle(element.closest("svg")!).zIndex,
    );
  const before = await layer();
  await page.getByRole("button", { name: "service API v1" }).click();
  await expect(page.getByTestId("selected-nodes")).toContainText("api");
  await expect(
    page.locator('.react-flow__node[data-id="api"] .sgc-node'),
  ).toHaveClass(/selected/);
  await waitForGalleryStable(page);
  expect(await layer()).toBe(before);
});

test("toolbar Fit View retains supported spacing after zooming", async ({
  page,
}) => {
  await openGallery(page);
  await page.locator(".react-flow__controls-zoomin").click();
  await page.locator(".react-flow__controls-fitview").click();
  await waitForGalleryStable(page);
  await expect
    .poll(async () =>
      page.locator(".react-flow").evaluate((flow) => {
        const viewport = flow.querySelector(".react-flow__viewport")!;
        const zoom = new DOMMatrixReadOnly(getComputedStyle(viewport).transform)
          .a;
        const boxes = [...flow.querySelectorAll(".react-flow__node")].map(
          (node) => node.getBoundingClientRect(),
        );
        const width =
          (Math.max(...boxes.map((box) => box.right)) -
            Math.min(...boxes.map((box) => box.left))) /
          zoom;
        const height =
          (Math.max(...boxes.map((box) => box.bottom)) -
            Math.min(...boxes.map((box) => box.top))) /
          zoom;
        const expected = Math.max(
          0.08,
          Math.min(
            2.5,
            flow.clientWidth / (width * 1.1),
            flow.clientHeight / (height * 1.1),
          ),
        );
        return Math.abs(zoom - expected);
      }),
    )
    .toBeLessThan(0.003);
});

test("default wheel, pinch and double-click zoom remain available", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await openGallery(page);
  const flow = page.locator(".react-flow");
  const zoom = () =>
    flow
      .locator(".react-flow__viewport")
      .evaluate((e) => new DOMMatrixReadOnly(getComputedStyle(e).transform).a);
  for (const gesture of ["wheel", "pinch", "double-click"]) {
    await flow.locator(".react-flow__controls-fitview").click();
    await waitForGalleryStable(page);
    const before = await zoom();
    const box = await flow.boundingBox();
    await page.mouse.move(box!.x + box!.width - 30, box!.y + box!.height / 2);
    if (gesture === "double-click")
      await page.mouse.dblclick(
        box!.x + box!.width - 30,
        box!.y + box!.height / 2,
      );
    else {
      if (gesture === "pinch") await page.keyboard.down("Control");
      await page.mouse.wheel(0, -120);
      if (gesture === "pinch") await page.keyboard.up("Control");
    }
    await expect.poll(zoom).toBeGreaterThan(before + 0.05);
    expect(await zoom()).toBeLessThanOrEqual(2.5);
  }
});
