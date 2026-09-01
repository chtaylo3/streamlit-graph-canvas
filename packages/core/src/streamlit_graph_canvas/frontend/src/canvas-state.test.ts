import { beforeEach, describe, expect, it } from "vitest";
import {
  clearCanvasStateForTests,
  loadCanvasState,
  selectNode,
  storeCanvasState,
} from "./canvas-state";
import { clickAction } from "./events";

beforeEach(clearCanvasStateForTests);

describe("persistent canvas state", () => {
  it("restores browser state and reconciles removed nodes", () => {
    storeCanvasState("canvas", {
      selectedNodeIds: ["a", "removed"],
      viewport: { x: 4, y: 5, zoom: 1.2 },
      acknowledgedSeq: 3,
      topologyHash: "old",
      nextSeq: 4,
      pendingActions: [],
    });
    const loaded = loadCanvasState(
      "canvas",
      { selectedNodeIds: [], viewport: null, acknowledgedSeq: 2 },
      "new",
      new Set(["a"]),
    );
    expect(loaded.topologyChanged).toBe(true);
    expect(loaded.state.selectedNodeIds).toEqual(["a"]);
    expect(loaded.state.acknowledgedSeq).toBe(3);
  });

  it("implements all selection modes", () => {
    expect(selectNode([], "a", "none")).toEqual([]);
    expect(selectNode(["b"], "a", "single")).toEqual(["a"]);
    expect(selectNode(["a"], "a", "multiple")).toEqual([]);
    expect(selectNode(["a"], "b", "multiple")).toEqual(["a", "b"]);
  });

  it("retains only actions above the server acknowledgement", () => {
    storeCanvasState("canvas", {
      selectedNodeIds: [],
      viewport: null,
      acknowledgedSeq: 1,
      topologyHash: "same",
      nextSeq: 2,
      pendingActions: [
        clickAction(
          2,
          "a",
          "service",
          1,
          { shift: false, meta: false, alt: false },
          "00000000-0000-4000-8000-000000000000",
        ),
      ],
    });
    const loaded = loadCanvasState(
      "canvas",
      { selectedNodeIds: [], viewport: null, acknowledgedSeq: 2 },
      "same",
      new Set(["a"]),
    );
    expect(loaded.state.pendingActions).toEqual([]);
    expect(loaded.state.nextSeq).toBe(2);
  });
});
