import { useCallback, useEffect, useMemo, useState } from "react";
import type { Node, NodeChange } from "@xyflow/react";

/** Retain React Flow's measurements when replacing controlled node objects.
 * Omitting measured resets its cached handle bounds, even at unchanged sizes.
 */
export function useMeasuredNodes<N extends Node>(nodes: N[]) {
  const [measurements, setMeasurements] = useState(
    new Map<string, { width: number; height: number }>(),
  );
  const ids = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);

  useEffect(() => {
    setMeasurements((previous) => {
      if ([...previous.keys()].every((id) => ids.has(id))) return previous;
      return new Map([...previous].filter(([id]) => ids.has(id)));
    });
  }, [ids]);

  const onNodesChange = useCallback(
    (changes: NodeChange<N>[]) => {
      setMeasurements((previous) => {
        let next = previous;
        for (const change of changes) {
          if (
            change.type !== "dimensions" ||
            !change.dimensions ||
            !ids.has(change.id)
          )
            continue;
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
      });
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
