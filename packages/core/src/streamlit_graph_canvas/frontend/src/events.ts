import {
  MAX_ACTION_BATCH,
  MAX_BROWSER_STATE_BYTES,
  MAX_IDENTIFIER_CHARS,
  PROTOCOL_VERSION,
} from "./contract";

export type CanvasAction = {
  protocolVersion: typeof PROTOCOL_VERSION;
  seq: number;
  operationId: string;
  gesture: "click";
  nodeId: string;
  nodeType: string;
  topologyRevision: number;
  target: { kind: "node" };
  modifiers: { shift: boolean; meta: boolean; alt: boolean };
};

export function clickAction(
  seq: number,
  nodeId: string,
  nodeType: string,
  topologyRevision: number,
  modifiers: CanvasAction["modifiers"],
  operationId = crypto.randomUUID(),
): CanvasAction {
  if (
    nodeId.length === 0
    || nodeId.length > MAX_IDENTIFIER_CHARS
    || nodeType.length === 0
    || nodeType.length > MAX_IDENTIFIER_CHARS
  ) {
    throw new Error("SGC_ACTION_NODE_LIMIT: node identifiers exceed the contract");
  }
  return {
    protocolVersion: PROTOCOL_VERSION,
    seq,
    operationId,
    gesture: "click",
    nodeId,
    nodeType,
    topologyRevision,
    target: { kind: "node" },
    modifiers,
  };
}

export function appendPendingAction(
  actions: readonly CanvasAction[],
  action: CanvasAction,
): CanvasAction[] {
  if (actions.length >= MAX_ACTION_BATCH) {
    throw new Error("SGC_ACTION_BATCH_LIMIT: pending action queue is full");
  }
  const pending = [...actions, action];
  if (new TextEncoder().encode(JSON.stringify(pending)).byteLength > MAX_BROWSER_STATE_BYTES) {
    throw new Error("SGC_ACTION_BYTES_LIMIT: pending action queue is too large");
  }
  return pending;
}

export type ActionQueue = {
  nextSeq: number;
  pending: CanvasAction[];
};

/**
 * Reconcile the browser action queue with Python's acknowledged sequence.
 *
 * Acknowledged actions are dropped, unacknowledged ones are kept for replay,
 * and the sequence counter never moves backwards, so a stale or reordered
 * acknowledgement can neither resurrect old actions nor reuse a number.
 */
export function reconcileActionQueue(
  queue: ActionQueue,
  acknowledgedSeq: number,
): ActionQueue {
  return {
    nextSeq: Math.max(queue.nextSeq, acknowledgedSeq),
    pending: queue.pending.filter((action) => action.seq > acknowledgedSeq),
  };
}
