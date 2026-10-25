import type { NodeChange } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { snapshotMeasurements } from "./react-flow-compat";
import { retainMeasurements } from "./use-measured-nodes";

describe("React Flow measurement boundary", () => {
  it("owns dimensions even when the upstream payload is mutated after dispatch", () => {
    const dimensions = { width: 120, height: 60 };
    const changes: NodeChange[] = [
      { type: "dimensions", id: "a", dimensions },
      { type: "select", id: "a", selected: true },
    ];
    const snapshot = snapshotMeasurements(changes);
    dimensions.width = 999;
    changes.length = 0;
    const previous = new Map();
    const liveIds = new Set(["a"]);
    const first = retainMeasurements(previous, snapshot, liveIds);
    const replayed = retainMeasurements(previous, snapshot, liveIds);
    expect([...first]).toEqual([["a", { width: 120, height: 60 }]]);
    expect(replayed).toEqual(first);
    expect(previous.size).toBe(0);
  });

  it("consumes a one-shot container before queuing repeatable state updates", () => {
    function* notifications(): IterableIterator<NodeChange> {
      yield {
        type: "dimensions",
        id: "a",
        dimensions: { width: 120, height: 60 },
      };
      yield {
        type: "dimensions",
        id: "a",
        dimensions: { width: 180, height: 90 },
      };
      yield { type: "remove", id: "a" };
    }
    const source = notifications();
    const snapshot = snapshotMeasurements(source);
    expect([...source]).toEqual([]);
    for (let replay = 0; replay < 2; replay++) {
      const next = retainMeasurements(new Map(), snapshot, new Set(["a"]));
      expect(next.get("a")).toEqual({ width: 180, height: 90 });
    }
  });
});
