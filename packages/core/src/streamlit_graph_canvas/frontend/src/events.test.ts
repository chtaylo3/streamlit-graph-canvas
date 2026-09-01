import { describe, expect, it } from "vitest";
import { MAX_ACTION_BATCH } from "./contract";
import { appendPendingAction, clickAction } from "./events";

describe("action protocol", () => {
  it("creates the exact v1 click envelope", () => {
    expect(
      clickAction(
        4,
        "api",
        "service",
        2,
        { shift: true, meta: false, alt: false },
        "00000000-0000-4000-8000-000000000000",
      ),
    ).toEqual({
      protocolVersion: 1,
      seq: 4,
      operationId: "00000000-0000-4000-8000-000000000000",
      gesture: "click",
      nodeId: "api",
      nodeType: "service",
      topologyRevision: 2,
      target: { kind: "node" },
      modifiers: { shift: true, meta: false, alt: false },
    });
  });

  it("bounds identifiers and the pending action queue", () => {
    const value = clickAction(
      1,
      "api",
      "service",
      2,
      { shift: false, meta: false, alt: false },
      "00000000-0000-4000-8000-000000000000",
    );
    expect(appendPendingAction([], value)).toEqual([value]);
    expect(() => appendPendingAction(Array(MAX_ACTION_BATCH).fill(value), value))
      .toThrow("SGC_ACTION_BATCH_LIMIT");
    expect(() => clickAction(
      1,
      "x".repeat(513),
      "service",
      2,
      { shift: false, meta: false, alt: false },
    )).toThrow("SGC_ACTION_NODE_LIMIT");
  });
});
