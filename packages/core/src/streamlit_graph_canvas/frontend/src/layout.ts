import ELK from "elkjs/lib/elk.bundled.js";

export type LayoutNode = { id: string; width: number; height: number };
export type LayoutEdge = { id: string; source: string; target: string };

const elk = new ELK();

export async function layoutGraph(nodes: LayoutNode[], edges: LayoutEdge[]) {
  const ids = new Set<string>();
  for (const node of nodes) {
    if (
      !node.id ||
      ids.has(node.id) ||
      !Number.isFinite(node.width) ||
      !Number.isFinite(node.height) ||
      node.width <= 0 ||
      node.height <= 0
    ) {
      throw new Error(`SGC_LAYOUT_NODE_INVALID: ${node.id || "<empty>"}`);
    }
    ids.add(node.id);
  }
  const edgeIds = new Set<string>();
  for (const edge of edges) {
    if (
      !edge.id ||
      edgeIds.has(edge.id) ||
      !ids.has(edge.source) ||
      !ids.has(edge.target)
    ) {
      throw new Error(`SGC_LAYOUT_EDGE_INVALID: ${edge.id || "<empty>"}`);
    }
    edgeIds.add(edge.id);
  }
  const result = await elk.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": "48",
      "elk.layered.spacing.nodeNodeBetweenLayers": "90",
    },
    children: nodes.map((node) => ({ ...node })),
    edges: edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  });
  return new Map(
    result.children?.map((node) => [
      node.id,
      { x: node.x ?? 0, y: node.y ?? 0 },
    ]) ?? [],
  );
}
