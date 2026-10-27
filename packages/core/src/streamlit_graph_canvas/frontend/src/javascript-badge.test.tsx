// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JavascriptBadge, type JavascriptBadgeView } from "./javascript-badge";
import type {
  JavascriptRendererFactory,
  JavascriptRendererRegistration,
} from "./javascript-registry";

afterEach(cleanup);

const badge: JavascriptBadgeView = {
  name: "count",
  region: { x: 4, y: 6, width: 40, height: 20 },
  data: 7,
  options: { prefix: "+" },
};
const palette = { accent: { light: "#2563eb", dark: "#60a5fa" } };
const registration = (render: JavascriptRendererFactory): JavascriptRendererRegistration => ({
  kind: "example/fixture/badge",
  rendererApi: 1,
  version: "1.0.0",
  buildIdentity: "a".repeat(64),
  render,
});

function svgOf(container: HTMLElement) {
  return container.querySelector("svg.sgc-badge") as SVGSVGElement;
}

describe("JavascriptBadge", () => {
  it("renders into an isolated, sized SVG with resolved palette tones", () => {
    const factory = vi.fn<JavascriptRendererFactory>(({ target }) => {
      target.append(document.createElementNS("http://www.w3.org/2000/svg", "circle"));
    });
    const { container } = render(
      <JavascriptBadge badge={badge} palette={palette} registration={registration(factory)} />,
    );
    const svg = svgOf(container);
    expect(svg.querySelector("circle")).not.toBeNull();
    expect(svg.getAttribute("data-sgc-badge")).toBe("count");
    expect(svg.getAttribute("data-sgc-render-error")).toBeNull();
    expect(svg.getAttribute("viewBox")).toBe("0 0 40 20");
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    const context = factory.mock.calls[0][0];
    expect(context.target).toBe(svg);
    expect(context.data).toBe(7);
    expect(context.options).toEqual({ prefix: "+" });
    expect(context.region).toEqual(badge.region);
    // Renderers receive resolved CSS colors, never raw palette objects.
    expect(context.palette).toEqual({ accent: "light-dark(#2563eb, #60a5fa)" });
  });

  it("isolates a throwing renderer and clears anything it drew", () => {
    const factory: JavascriptRendererFactory = ({ target }) => {
      target.append(document.createElementNS("http://www.w3.org/2000/svg", "rect"));
      throw new Error("renderer bug");
    };
    const { container } = render(
      <JavascriptBadge badge={badge} palette={palette} registration={registration(factory)} />,
    );
    const svg = svgOf(container);
    expect(svg.getAttribute("data-sgc-render-error")).toBe("true");
    expect(svg.childNodes).toHaveLength(0);
  });

  it("recovers after a failing renderer is replaced", () => {
    const failing = registration(() => {
      throw new Error("boom");
    });
    const working = registration(({ target }) => {
      target.append(document.createElementNS("http://www.w3.org/2000/svg", "path"));
    });
    const view = render(<JavascriptBadge badge={badge} palette={palette} registration={failing} />);
    view.rerender(<JavascriptBadge badge={badge} palette={palette} registration={working} />);
    const svg = svgOf(view.container);
    expect(svg.getAttribute("data-sgc-render-error")).toBeNull();
    expect(svg.querySelector("path")).not.toBeNull();
  });

  it("runs renderer cleanup on unmount and contains cleanup errors", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const cleanupSpy = vi.fn(() => {
      throw new Error("cleanup bug");
    });
    const view = render(
      <JavascriptBadge badge={badge} palette={palette} registration={registration(() => cleanupSpy)} />,
    );
    try {
      expect(() => view.unmount()).not.toThrow();
      expect(cleanupSpy).toHaveBeenCalledTimes(1);
      expect(errors).toHaveBeenCalledWith("SGC_JAVASCRIPT_CLEANUP_ERROR", "cleanup bug");
    } finally {
      errors.mockRestore();
    }
  });
});
