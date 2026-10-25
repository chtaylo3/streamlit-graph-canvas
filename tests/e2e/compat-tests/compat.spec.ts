import { test, expect, waitForGalleryStable } from "../tests/harness";
import type { Locator, Page } from "@playwright/test";

const primary = (page: Page) => page.locator(".sgc-root").first();
const node = (canvas: Locator, id: string) =>
  canvas.locator(`.react-flow__node[data-id="${id}"]`);
const settle = (page: Page, count = 2) => waitForGalleryStable(page, count);
async function expand(page: Page, id: string) {
  await node(primary(page), id).locator(".sgc-group-marker").click();
  await settle(page);
  await primary(page).locator(".react-flow__controls-fitview").click();
  await settle(page);
}
async function namedAttachment(canvas: Locator) {
  await expect(
    canvas.locator('.react-flow__edge[data-id="named"]'),
  ).toBeVisible();
  await expect
    .poll(() =>
      canvas.evaluate((root) => {
        const path = root.querySelector<SVGPathElement>(
          '.react-flow__edge[data-id="named"] .react-flow__edge-path',
        )!;
        const matrix = path.getScreenCTM()!;
        const start = path.getPointAtLength(0).matrixTransform(matrix),
          end = path
            .getPointAtLength(path.getTotalLength())
            .matrixTransform(matrix);
        const bounds = (id: string, type: string, handle: string) =>
          root
            .querySelector(
              `.react-flow__node[data-id="${id}"] .react-flow__handle.${type}[data-handleid="${handle}"]`,
            )!
            .getBoundingClientRect();
        const a = bounds("leaf-0-0", "source", "out"),
          b = bounds("leaf-0-1", "target", "in");
        return Math.max(
          // React Flow attaches bottom/top ports at their outer edge.
          Math.hypot(start.x - a.x - a.width / 2, start.y - a.bottom),
          Math.hypot(end.x - b.x - b.width / 2, end.y - b.top),
        );
      }),
    )
    .toBeLessThan(2);
}
async function nesting(canvas: Locator) {
  const errors = await canvas
    .locator(".react-flow__node")
    .evaluateAll((elements) => {
      const rects = new Map(
        elements.map((e) => [
          e.getAttribute("data-id")!,
          e.getBoundingClientRect(),
        ]),
      );
      return [
        ["branch-0", "root"],
        ["leaf-0-0", "branch-0"],
        ["leaf-0-1", "branch-0"],
      ].filter(([child, owner]) => {
        const c = rects.get(child)!,
          p = [...rects].find(([id]) =>
            id.startsWith("sgc-group:" + owner + "\0"),
          )?.[1];
        return (
          !c ||
          !p ||
          c.left < p.left - 1 ||
          c.top < p.top - 1 ||
          c.right > p.right + 1 ||
          c.bottom > p.bottom + 1
        );
      });
    });
  expect(errors).toEqual([]);
}

async function groupedEdgeStacking(canvas: Locator) {
  const layers = await canvas.evaluate((root) => {
    const nodeLayer = (id: string) =>
      Number(
        getComputedStyle(
          root.querySelector(`.react-flow__node[data-id="${id}"]`)!,
        ).zIndex,
      );
    const edgeLayer = (id: string) =>
      Number(
        getComputedStyle(
          root
            .querySelector(`.react-flow__edge[data-id="${id}"]`)!
            .closest("svg")!,
        ).zIndex,
      );
    return {
      expected: Math.max(nodeLayer("leaf-0-0"), nodeLayer("leaf-0-1")),
      named: edgeLayer("named"),
      overlap: edgeLayer("overlap"),
    };
  });
  // Both majors elevate grouped edges with their endpoint node layer so they
  // stay above the group background, even with elevateEdgesOnSelect disabled.
  expect(layers.named).toBe(layers.expected);
  expect(layers.overlap).toBe(layers.named);
}

test("nested groups retain sizing and named attachments through resize, rerun, removal and reappearance", async ({
  page,
}) => {
  await page.goto("/");
  await settle(page);
  await expand(page, "root");
  await expand(page, "branch-0");
  await nesting(primary(page));
  await namedAttachment(primary(page));
  const input = page.getByRole("spinbutton", {
    name: "Branch width",
    exact: true,
  });
  await input.fill("320");
  await input.press("Enter");
  await settle(page);
  await expect(node(primary(page), "branch-0")).toHaveCSS("width", "320px");
  await nesting(primary(page));
  await namedAttachment(primary(page));
  await page.getByRole("button", { name: "Update presentation" }).click();
  await settle(page);
  await namedAttachment(primary(page));
  await page
    .getByRole("checkbox", { name: "Include first leaf" })
    .press("Space");
  await settle(page);
  await expect(node(primary(page), "leaf-0-0")).toHaveCount(0);
  const width = page.getByRole("spinbutton", {
    name: "Leaf width",
    exact: true,
  });
  await width.fill("260");
  await width.press("Enter");
  await settle(page);
  await page
    .getByRole("checkbox", { name: "Include first leaf" })
    .press("Space");
  await settle(page);
  await expect(node(primary(page), "leaf-0-0")).toHaveCSS("width", "260px");
  await namedAttachment(primary(page));
  await nesting(primary(page));
  await groupedEdgeStacking(primary(page));
  await node(primary(page), "leaf-0-0").locator(".sgc-node").click();
  await settle(page);
  await groupedEdgeStacking(primary(page));
  await namedAttachment(primary(page));
  await node(primary(page), "branch-0").locator(".sgc-group-marker").click();
  await settle(page);
  await expect(node(primary(page), "leaf-0-0")).toHaveCount(0);
});

test("user zoom interrupts a pending controlled transition without reverting the viewport", async ({
  page,
}) => {
  await page.goto("/");
  await settle(page);
  await expand(page, "root");
  const duration = page.getByRole("spinbutton", {
    name: "Transition duration",
  });
  await duration.fill("1000");
  await duration.press("Enter");
  await settle(page);
  const width = page.getByRole("spinbutton", {
    name: "Branch width",
    exact: true,
  });
  await width.fill("360");
  await width.press("Enter");
  await expect(primary(page)).toHaveAttribute("data-sgc-transition", "running");
  await primary(page).locator(".react-flow__controls-zoomin").click();
  const viewport = await primary(page)
    .locator(".react-flow__viewport")
    .getAttribute("style");
  await settle(page);
  expect(
    await primary(page).locator(".react-flow__viewport").getAttribute("style"),
  ).toBe(viewport);
  await expect(node(primary(page), "branch-0")).toHaveCSS("width", "360px");
});

test("repeated primary teardown preserves its viewport and secondary independence without duplicate actions", async ({
  page,
}) => {
  await page.goto("/");
  await settle(page);
  const secondary = page.locator(".sgc-root").last();
  const otherViewport = await secondary
    .locator(".react-flow__viewport")
    .getAttribute("style");
  await primary(page).locator(".react-flow__controls-zoomin").click();
  await settle(page);
  const viewport = await primary(page)
    .locator(".react-flow__viewport")
    .getAttribute("style");
  for (let cycle = 0; cycle < 2; cycle++) {
    await page.getByRole("checkbox", { name: "Mount primary" }).press("Space");
    await settle(page, 1);
    expect(
      await page
        .locator(".sgc-root")
        .locator(".react-flow__viewport")
        .getAttribute("style"),
    ).toBe(otherViewport);
    await page.getByRole("checkbox", { name: "Mount primary" }).press("Space");
    await settle(page);
    expect(
      await primary(page)
        .locator(".react-flow__viewport")
        .getAttribute("style"),
    ).toBe(viewport);
    await node(primary(page), "root").locator(".sgc-node").click();
    await settle(page);
    await expect(page.getByTestId("actions-primary")).toHaveText(
      String(cycle + 1),
    );
    await expect(page.getByTestId("actions-secondary")).toHaveText("0");
    expect(
      await secondary.locator(".react-flow__viewport").getAttribute("style"),
    ).toBe(otherViewport);
  }
});

test("new topology and presentation updates supersede a pending scene without reviving removed nodes", async ({
  page,
}) => {
  await page.goto("/");
  await settle(page);
  await expand(page, "root");
  await expand(page, "branch-0");
  const duration = page.getByRole("spinbutton", {
    name: "Transition duration",
  });
  await duration.fill("1000");
  await duration.press("Enter");
  await settle(page);
  const width = page.getByRole("spinbutton", {
    name: "Branch width",
    exact: true,
  });
  await width.fill("300");
  await width.press("Enter");
  await expect(primary(page)).toHaveAttribute("data-sgc-transition", "running");
  await page
    .getByRole("checkbox", { name: "Include first leaf" })
    .press("Space");
  await page
    .getByRole("button", { name: "Update presentation" })
    .press("Enter");
  await settle(page);
  await expect(node(primary(page), "root")).toContainText("Root 1");
  await expect(node(primary(page), "branch-0")).toHaveCSS("width", "300px");
  await expect(node(primary(page), "leaf-0-0")).toHaveCount(0);
  await expect(
    primary(page).locator('.react-flow__edge[data-id="named"]'),
  ).toHaveCount(0);
  await page
    .getByRole("checkbox", { name: "Include first leaf" })
    .press("Space");
  await settle(page);
  await namedAttachment(primary(page));
  await nesting(primary(page));
  await node(primary(page), "leaf-0-0").locator(".sgc-node").press("Enter");
  await settle(page);
  await expect(page.getByTestId("actions-primary")).toHaveText("1");
  await expect(page.getByTestId("actions-secondary")).toHaveText("0");
});
