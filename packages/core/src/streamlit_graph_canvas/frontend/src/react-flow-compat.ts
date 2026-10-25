import type {
  FitViewOptions,
  Node,
  NodeChange,
  ReactFlowProps,
} from "@xyflow/react";

/** App-owned values: React Flow containers must not escape this boundary. */
export type Dimensions = Readonly<{ width: number; height: number }>;
export type MeasurementUpdate = Readonly<{
  id: string;
  dimensions: Dimensions;
}>;

/** Snapshot v12 arrays or v13 changesets before React queues/replays an updater. */
export function snapshotMeasurements<N extends Node>(
  changes: Iterable<NodeChange<N>>,
): MeasurementUpdate[] {
  const measurements: MeasurementUpdate[] = [];
  for (const change of changes) {
    if (change.type === "dimensions" && change.dimensions) {
      measurements.push({
        id: change.id,
        dimensions: { ...change.dimensions },
      });
    }
  }
  return measurements;
}

/** v12 ratio -> per-side percentage; numeric padding means pixels in v13. */
function percentagePadding(ratio: number): `${number}%` {
  return `${(ratio / (1 + ratio)) * 50}%`;
}

export const fitPadding = {
  initial: percentagePadding(0.12),
  search: percentagePadding(0.25),
  toolbar: percentagePadding(0.1),
} as const;

/** Explicit defaults preserve supported behavior when upstream defaults change. */
export const flowDefaults = {
  elevateEdgesOnSelect: false,
} satisfies Pick<ReactFlowProps, "elevateEdgesOnSelect">;

export const controlsFitViewOptions = {
  padding: fitPadding.toolbar,
} satisfies FitViewOptions;
