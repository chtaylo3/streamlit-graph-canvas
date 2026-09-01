import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanupJavascriptRenderer,
  rendererRegistry,
  requireJavascriptRenderer,
} from "./javascript-registry";

beforeEach(() => rendererRegistry().clear());

describe("JavaScript renderer registry", () => {
  it("accepts an exact manifest-bound registration", () => {
    rendererRegistry().set("vendor/package/badge", {
      kind: "vendor/package/badge",
      rendererApi: 1,
      version: "1.2.3",
      buildIdentity: "identity-a",
      render: () => undefined,
    });
    expect(requireJavascriptRenderer({
      kind: "vendor/package/badge",
      rendererApi: 1,
      version: "1.2.3",
      buildIdentity: "identity-a",
      assetHash: "content-hash-a",
      component: "vendor.renderer_bootstrap",
      entry: "bootstrap.js",
    })).not.toBeNull();
  });

  it("fails closed on a conflicting asset identity", () => {
    const render = vi.fn();
    rendererRegistry().set("vendor/package/badge", {
      kind: "vendor/package/badge",
      rendererApi: 1,
      version: "1.2.3",
      buildIdentity: "identity-wrong",
      render,
    });
    expect(() => requireJavascriptRenderer({
      kind: "vendor/package/badge",
      rendererApi: 1,
      version: "1.2.3",
      buildIdentity: "identity-expected",
      assetHash: "content-hash-expected",
      component: "vendor.renderer_bootstrap",
      entry: "bootstrap.js",
    })).toThrow(/SGC_JAVASCRIPT_REGISTRATION_CONFLICT/);
    expect(render).not.toHaveBeenCalled();
  });
});

describe("JavaScript renderer cleanup", () => {
  it("clears renderer output even when trusted cleanup throws", () => {
    const replaceChildren = vi.fn();
    const target = { replaceChildren } as unknown as SVGSVGElement;
    const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() => cleanupJavascriptRenderer(() => {
      throw new Error("fixture failure");
    }, target)).not.toThrow();

    expect(replaceChildren).toHaveBeenCalledOnce();
    expect(report).toHaveBeenCalledWith(
      "SGC_JAVASCRIPT_CLEANUP_ERROR",
      "fixture failure",
    );
    report.mockRestore();
  });
});
