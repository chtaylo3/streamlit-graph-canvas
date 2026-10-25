import type { Node, NodeChange, OnNodesChange } from "@xyflow/react";
import * as xyflow from "@xyflow/react";
import { describe, expect, expectTypeOf, it } from "vitest";
import {
  pruneMeasurements,
  retainMeasurements,
  useMeasuredNodes,
} from "./use-measured-nodes";

type CustomNode = Node<{ label: string }, "custom">;

// This checks the installed v12 or v13 callback contract during each lane's build.
expectTypeOf<
  ReturnType<typeof useMeasuredNodes<CustomNode>>["onNodesChange"]
>().toEqualTypeOf<OnNodesChange<CustomNode>>();

const ids = new Set(["a", "b"]);
const dimensions = { width: 120, height: 60 };

// Exercise the actual prerelease class when this suite runs against v13.
const NodeChangeset = (
  "NodeChangeset" in xyflow ? xyflow.NodeChangeset : null
) as (new (changes: NodeChange[]) => Iterable<NodeChange>) | null;

it.skipIf(!NodeChangeset)(
  "retains measurements from a real v13 NodeChangeset",
  () => {
    const previous = new Map([["b", dimensions]]);
    const changes = new NodeChangeset!([
      { id: "a", type: "dimensions", dimensions },
      { id: "b", type: "select", selected: true },
    ]);
    const next = retainMeasurements(previous, changes, ids);
    expect([...next]).toEqual([
      ["b", dimensions],
      ["a", dimensions],
    ]);
    expect(previous.has("a")).toBe(false);
  },
);

function iterable(changes: NodeChange[]): Iterable<NodeChange> {
  return {
    *[Symbol.iterator]() {
      yield* changes;
    },
  };
}

describe("stale measurement cleanup", () => {
  it("removes only deleted IDs without mutating the previous cache", () => {
    const previous = new Map([
      ["a", dimensions],
      ["b", dimensions],
    ]);
    const next = pruneMeasurements(previous, new Set(["b", "new"]));
    expect([...next]).toEqual([["b", dimensions]]);
    expect(next.get("b")).toBe(previous.get("b"));
    expect(previous.has("a")).toBe(true);
    expect(pruneMeasurements(next, new Set())).toEqual(new Map());
  });

  it("keeps cache identity when every measured node is still present", () => {
    const previous = new Map([["a", dimensions]]);
    expect(pruneMeasurements(previous, ids)).toBe(previous);
    const empty = new Map();
    expect(pruneMeasurements(empty, ids)).toBe(empty);
  });

  it("requires a fresh measurement when a deleted ID reappears", () => {
    const previous = new Map([["a", dimensions]]);
    const removed = pruneMeasurements(previous, new Set(["b"]));
    const reappeared = pruneMeasurements(removed, ids);
    expect(reappeared.has("a")).toBe(false);
    const resized = { width: 240, height: 100 };
    const measured = retainMeasurements(
      reappeared,
      [{ id: "a", type: "dimensions", dimensions: resized }],
      ids,
    );
    expect(measured.get("a")).toEqual(resized);
    expect(reappeared.has("a")).toBe(false);
    expect(previous.get("a")).toBe(dimensions);
  });
});

describe.each([
  ["v12 arrays", (changes: NodeChange[]) => changes],
  ["v13-style iterable changesets", iterable],
] as const)("measurement retention with %s", (_name, payload) => {
  it("retains measurements without mutating the previous state", () => {
    const previous = new Map([["b", dimensions]]);
    const next = retainMeasurements(
      previous,
      payload([{ id: "a", type: "dimensions", dimensions }]),
      ids,
    );
    expect(next).not.toBe(previous);
    expect(next.get("a")).toEqual(dimensions);
    expect(next.get("b")).toBe(previous.get("b"));
    expect(previous.has("a")).toBe(false);
  });

  it("uses the last measurement for each node in a batch", () => {
    const resized = { width: 180, height: 90 };
    const next = retainMeasurements(
      new Map(),
      payload([
        { id: "a", type: "dimensions", dimensions },
        { id: "b", type: "dimensions", dimensions },
        { id: "a", type: "dimensions", dimensions: resized },
      ]),
      ids,
    );
    expect([...next]).toEqual([
      ["a", resized],
      ["b", dimensions],
    ]);
  });

  it("ignores unrelated changes, missing dimensions, and absent nodes", () => {
    const previous = new Map([["a", dimensions]]);
    const node: Node = { id: "b", position: { x: 0, y: 0 }, data: {} };
    expect(
      retainMeasurements(
        previous,
        payload([
          { id: "a", type: "select", selected: true },
          { id: "a", type: "position", position: { x: 10, y: 20 } },
          { id: "a", type: "remove" },
          { id: "b", type: "replace", item: node },
          { id: "a", type: "dimensions", resizing: true },
          { id: "removed", type: "dimensions", dimensions },
        ]),
        ids,
      ),
    ).toBe(previous);
  });

  it("preserves state identity for empty and duplicate notifications", () => {
    const previous = new Map([["a", dimensions]]);
    expect(retainMeasurements(previous, payload([]), ids)).toBe(previous);
    expect(
      retainMeasurements(
        previous,
        payload([
          { id: "a", type: "dimensions", dimensions: { ...dimensions } },
        ]),
        ids,
      ),
    ).toBe(previous);
  });

  it("updates either dimension while retaining other nodes across batches", () => {
    const previous = new Map([
      ["a", dimensions],
      ["b", dimensions],
    ]);
    const wider = { ...dimensions, width: 240 };
    const taller = { ...wider, height: 100 };
    const first = retainMeasurements(
      previous,
      payload([{ id: "a", type: "dimensions", dimensions: wider }]),
      ids,
    );
    const next = retainMeasurements(
      first,
      payload([{ id: "a", type: "dimensions", dimensions: taller }]),
      ids,
    );
    expect(first.get("a")).toEqual(wider);
    expect(next.get("a")).toEqual(taller);
    expect(next.get("b")).toBe(dimensions);
    expect(previous.get("a")).toBe(dimensions);
  });
});
