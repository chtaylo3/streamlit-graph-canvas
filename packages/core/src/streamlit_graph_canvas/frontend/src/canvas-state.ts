import type { Viewport } from "@xyflow/react";
import { MAX_SELECTION } from "./contract";
import type { CanvasAction } from "./events";

export type ServerCanvasState = {
  selectedNodeIds: string[];
  viewport: Viewport | null;
  acknowledgedSeq: number;
};

export type BrowserCanvasState = ServerCanvasState & {
  topologyHash: string;
  nextSeq: number;
  pendingActions: CanvasAction[];
};

const browserState = new Map<string, BrowserCanvasState>();

export function loadCanvasState(
  key: string,
  server: ServerCanvasState,
  topologyHash: string,
  validNodeIds: ReadonlySet<string>,
): { state: BrowserCanvasState; topologyChanged: boolean } {
  const cached = browserState.get(key);
  const topologyChanged = cached !== undefined && cached.topologyHash !== topologyHash;
  const source = cached ?? {
    ...server,
    topologyHash,
    nextSeq: server.acknowledgedSeq,
    pendingActions: [],
  };
  const state = {
    selectedNodeIds: reconcileSelection(source.selectedNodeIds, validNodeIds),
    viewport: source.viewport,
    acknowledgedSeq: Math.max(source.acknowledgedSeq, server.acknowledgedSeq),
    nextSeq: Math.max(source.nextSeq, server.acknowledgedSeq),
    pendingActions: source.pendingActions.filter(
      (action) => action.seq > server.acknowledgedSeq,
    ),
    topologyHash,
  };
  browserState.set(key, state);
  return { state, topologyChanged };
}

export function storeCanvasState(key: string, state: BrowserCanvasState): void {
  browserState.set(key, state);
}

export function reconcileSelection(
  selected: readonly string[],
  validNodeIds: ReadonlySet<string>,
): string[] {
  return [...new Set(selected)]
    .filter((id) => validNodeIds.has(id))
    .slice(0, MAX_SELECTION);
}

export function selectNode(
  selected: readonly string[],
  nodeId: string,
  mode: "none" | "single" | "multiple",
): string[] {
  if (mode === "none") return [...selected];
  if (mode === "single") return [nodeId];
  if (!selected.includes(nodeId) && selected.length >= MAX_SELECTION) {
    return [...selected];
  }
  return selected.includes(nodeId)
    ? selected.filter((id) => id !== nodeId)
    : [...selected, nodeId];
}

export function clearCanvasStateForTests(): void {
  browserState.clear();
}
