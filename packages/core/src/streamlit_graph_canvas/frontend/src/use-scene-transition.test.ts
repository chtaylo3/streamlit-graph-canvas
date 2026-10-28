// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import type { Node, ReactFlowInstance, Viewport } from "@xyflow/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Scene } from "./transition";
import { useSceneTransition } from "./use-scene-transition";

const node = (id: string, x = 0): Node => ({
  id,
  position: { x, y: 0 },
  width: 100,
  height: 80,
  data: {},
});
const scene = (...nodes: Node[]): Scene => ({ nodes, edges: [] });

let frames: Map<number, FrameRequestCallback>;
let nextFrame: number;
let now: number;
let reducedMotion: boolean;

beforeEach(() => {
  frames = new Map();
  nextFrame = 1;
  now = 0;
  reducedMotion = false;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(nextFrame, callback);
    return nextFrame++;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn((id: number) => frames.delete(id)));
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("reduce") && reducedMotion,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Run every queued animation frame at the given timestamp. */
async function advanceTo(timestamp: number) {
  now = timestamp;
  await act(async () => {
    const pending = [...frames.entries()];
    frames.clear();
    for (const [, callback] of pending) callback(timestamp);
  });
}

function setup(overrides: Partial<Parameters<typeof useSceneTransition>[1]> = {}) {
  let viewport: Viewport = { x: 0, y: 0, zoom: 1 };
  const flow = {
    getViewport: vi.fn(() => viewport),
    setViewport: vi.fn(async (next: Viewport) => {
      viewport = next;
      return true;
    }),
  } as unknown as ReactFlowInstance & {
    setViewport: ReturnType<typeof vi.fn>;
  };
  const host = document.createElement("div");
  Object.defineProperty(host, "clientWidth", { value: 800 });
  Object.defineProperty(host, "clientHeight", { value: 600 });
  const onSettled = vi.fn();
  const options = {
    ready: true,
    maxElements: 100,
    hasSavedViewport: false,
    revision: "r1",
    layoutKey: "l1",
    duration: 400,
    anchor: null,
    fitView: "initial" as const,
    flow,
    host,
    onSettled,
    ...overrides,
  };
  const hook = renderHook(
    ({ target, opts }: { target: Scene; opts: typeof options }) => useSceneTransition(target, opts),
    { initialProps: { target: scene(node("a"), node("b", 200)), opts: options } },
  );
  return { hook, flow, host, onSettled, options };
}

describe("useSceneTransition", () => {
  it("settles the first scene immediately and fits an unsaved initial view", async () => {
    const { hook, flow, host, onSettled } = setup();
    await act(async () => {});
    expect(hook.result.current.scene.nodes.map((n) => n.id)).toEqual(["a", "b"]);
    expect(host.dataset.sgcTransition).toBe("idle");
    expect(host.dataset.sgcTransitionDuration).toBe("0");
    expect(flow.setViewport).toHaveBeenCalledTimes(1);
    expect(flow.setViewport.mock.calls[0][0]).not.toEqual({ x: 0, y: 0, zoom: 1 });
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(frames.size).toBe(0);
  });

  it.each([
    { fitView: "never" as const, hasSavedViewport: false },
    { fitView: "initial" as const, hasSavedViewport: true },
  ])("keeps the current viewport for fitView=$fitView saved=$hasSavedViewport", async (overrides) => {
    const { flow } = setup(overrides);
    await act(async () => {});
    expect(flow.setViewport).toHaveBeenCalledWith({ x: 0, y: 0, zoom: 1 });
  });

  it("animates later revisions frame by frame and settles at the target", async () => {
    const { hook, host, onSettled, options } = setup();
    await act(async () => {});
    onSettled.mockClear();
    hook.rerender({
      target: scene(node("a", 100), node("b", 200)),
      opts: { ...options, revision: "r2" },
    });
    expect(host.dataset.sgcTransition).toBe("running");
    expect(hook.result.current.running.current).toBe(true);
    await advanceTo(200);
    const middle = hook.result.current.scene.nodes.find((n) => n.id === "a")!;
    expect(middle.position.x).toBeGreaterThan(0);
    expect(middle.position.x).toBeLessThan(100);
    expect(onSettled).not.toHaveBeenCalled();
    await advanceTo(400);
    expect(hook.result.current.scene.nodes.find((n) => n.id === "a")!.position.x).toBe(100);
    expect(host.dataset.sgcTransition).toBe("idle");
    expect(hook.result.current.running.current).toBe(false);
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it("skips animation when the user prefers reduced motion", async () => {
    reducedMotion = true;
    const { hook, host, options } = setup();
    await act(async () => {});
    hook.rerender({ target: scene(node("a", 100)), opts: { ...options, revision: "r2" } });
    await act(async () => {});
    expect(host.dataset.sgcTransitionDuration).toBe("0");
    expect(frames.size).toBe(0);
  });

  it("cancels a running frame on unmount", async () => {
    const { hook, options } = setup();
    await act(async () => {});
    hook.rerender({ target: scene(node("a", 100)), opts: { ...options, revision: "r2" } });
    expect(frames.size).toBe(1);
    hook.unmount();
    expect(cancelAnimationFrame).toHaveBeenCalled();
    expect(frames.size).toBe(0);
  });

  it("stops driving the viewport once the user interrupts", async () => {
    const { hook, flow, options } = setup();
    await act(async () => {});
    flow.setViewport.mockClear();
    hook.rerender({ target: scene(node("a", 100)), opts: { ...options, revision: "r2" } });
    hook.result.current.interruptViewport();
    await advanceTo(200);
    await advanceTo(400);
    expect(flow.setViewport).not.toHaveBeenCalled();
  });

  it("makes nodes that left the target inert while the old scene is retained", async () => {
    const { hook, host, options } = setup();
    await act(async () => {});
    hook.rerender({ target: scene(node("a")), opts: { ...options, ready: false } });
    expect(host.dataset.sgcLayoutPending).toBe("true");
    const exiting = hook.result.current.scene.nodes.find((n) => n.id === "b")!;
    expect(exiting.selectable).toBe(false);
    expect(exiting.focusable).toBe(false);
    expect(exiting.domAttributes).toMatchObject({ inert: true, "aria-hidden": true });
    const kept = hook.result.current.scene.nodes.find((n) => n.id === "a")!;
    expect(kept.domAttributes).toBeUndefined();
  });
});
