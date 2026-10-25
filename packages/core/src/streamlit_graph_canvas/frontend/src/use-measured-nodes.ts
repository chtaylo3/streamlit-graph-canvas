import { useCallback, useEffect, useMemo, useState } from "react";
import type { Node, OnNodesChange } from "@xyflow/react";
import {
  snapshotMeasurements,
  type Dimensions,
  type MeasurementUpdate,
} from "./react-flow-compat";

type Measurements = Map<string, Dimensions>;

/** Deleted node IDs must not reuse cached dimensions if they reappear later. */
export function pruneMeasurements(
  previous: Measurements,
  ids: ReadonlySet<string>,
): Measurements {
  if ([...previous.keys()].every((id) => ids.has(id))) return previous;
  return new Map([...previous].filter(([id]) => ids.has(id)));
}

/** Only measurements belong to React Flow; the server owns other node state. */
export function retainMeasurements(
  previous: Measurements,
  changes: Iterable<MeasurementUpdate>,
  ids: ReadonlySet<string>,
): Measurements {
  let next = previous;
  for (const change of changes) {
    if (!ids.has(change.id)) continue;
    const before = next.get(change.id);
    if (
      before?.width === change.dimensions.width &&
      before?.height === change.dimensions.height
    )
      continue;
    if (next === previous) next = new Map(previous);
    next.set(change.id, change.dimensions);
  }
  return next;
}

/** Retain React Flow's measurements when replacing controlled node objects.
 * Omitting measured resets its cached handle bounds, even at unchanged sizes.
 */
export function useMeasuredNodes<N extends Node>(nodes: N[]) {
  const [measurements, setMeasurements] = useState(
    new Map<string, Dimensions>(),
  );
  const ids = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);

  useEffect(() => {
    setMeasurements((previous) => pruneMeasurements(previous, ids));
  }, [ids]);

  const onNodesChange = useCallback<OnNodesChange<N>>(
    (changes) => {
      const snapshot = snapshotMeasurements(changes);
      setMeasurements((previous) =>
        retainMeasurements(previous, snapshot, ids),
      );
    },
    [ids],
  );

  const measuredNodes = useMemo(
    () =>
      nodes.map((node) => ({ ...node, measured: measurements.get(node.id) })),
    [nodes, measurements],
  );
  return { nodes: measuredNodes, onNodesChange };
}
