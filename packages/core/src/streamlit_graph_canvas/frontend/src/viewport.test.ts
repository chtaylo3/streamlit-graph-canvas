import { getViewportForBounds } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { controlsFitViewOptions, fitPadding } from "./react-flow-compat";

describe("viewport padding across React Flow versions", () => {
  it("keeps the initial fit clear of controls at the supported zoom", () => {
    const viewport = getViewportForBounds(
      { x: 12, y: 12, width: 500, height: 316 },
      704,
      620,
      0.08,
      2.5,
      fitPadding.initial,
    );
    expect(viewport.zoom).toBeCloseTo(1.26);
    expect(viewport.x).toBeCloseTo(21.88);
    expect(viewport.y).toBeCloseTo(95.8);
  });

  it("retains search navigation spacing and zoom limits", () => {
    const bounds = { x: 0, y: 0, width: 1000, height: 1000 };
    const viewport = getViewportForBounds(
      bounds,
      1000,
      1000,
      0.08,
      1.5,
      fitPadding.search,
    );
    expect(viewport.zoom).toBeCloseTo(0.8, 2);
    expect(viewport.x).toBeCloseTo(viewport.y);
    expect(viewport.x).toBeGreaterThanOrEqual(99);
    expect(
      getViewportForBounds(
        { ...bounds, width: 10, height: 10 },
        1000,
        1000,
        0.08,
        1.5,
        fitPadding.search,
      ).zoom,
    ).toBe(1.5);
  });

  it("preserves the v12 toolbar fit instead of inheriting new upstream defaults", () => {
    const viewport = getViewportForBounds(
      { x: 0, y: 0, width: 1000, height: 1000 },
      1000,
      1000,
      0.08,
      2.5,
      controlsFitViewOptions.padding,
    );
    expect(viewport.zoom).toBeCloseTo(1 / 1.1, 2);
    expect(viewport.x).toBeCloseTo(viewport.y);
    expect(viewport.x).toBeGreaterThanOrEqual(44);
    expect(viewport.x).toBeLessThanOrEqual(46);
  });
});
