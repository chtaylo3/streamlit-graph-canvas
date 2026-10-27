import { describe, expect, it } from "vitest";
import { MAX_ACTION_BATCH } from "./contract";
import {
  appendPendingAction,
  clickAction,
  reconcileActionQueue,
  type CanvasAction,
} from "./events";

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

describe("action queue reconciliation", () => {
  const none = { shift: false, meta: false, alt: false };
  const at = (seq: number): CanvasAction =>
    clickAction(seq, "api", "service", 1, none, `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`);
  const queue = (nextSeq: number, ...seqs: number[]) => ({
    nextSeq,
    pending: seqs.map(at),
  });
  const seqs = (value: { pending: CanvasAction[] }) => value.pending.map((a) => a.seq);

  it("drops acknowledged actions and keeps the rest for replay", () => {
    const next = reconcileActionQueue(queue(4, 2, 3, 4), 2);
    expect(seqs(next)).toEqual([3, 4]);
    expect(next.nextSeq).toBe(4);
  });

  it("keeps everything when nothing new is acknowledged", () => {
    const original = queue(3, 1, 2, 3);
    const next = reconcileActionQueue(original, 0);
    expect(seqs(next)).toEqual([1, 2, 3]);
    expect(next.pending).not.toBe(original.pending);
  });

  it("never moves the sequence backwards on a stale acknowledgement", () => {
    const acknowledged = reconcileActionQueue(queue(5, 4, 5), 5);
    expect(acknowledged).toEqual({ nextSeq: 5, pending: [] });
    // An out-of-order, older acknowledgement arrives after a newer one.
    const stale = reconcileActionQueue(acknowledged, 3);
    expect(stale).toEqual({ nextSeq: 5, pending: [] });
  });

  it("adopts a newer server sequence after a remount lost local state", () => {
    // A fresh mount starts at 0 but Python already acknowledged 7, so the next
    // click must be 8 rather than reusing an acknowledged number.
    expect(reconcileActionQueue(queue(0), 7)).toEqual({ nextSeq: 7, pending: [] });
  });
});
