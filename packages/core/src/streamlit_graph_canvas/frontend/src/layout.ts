import ELK from "elkjs/lib/elk.bundled.js";

export type LayoutNode = {
  id: string;
  width: number;
  height: number;
  layoutOrder?: number | null;
  /** Preserve explicitly applied match order when packing disconnected members. */
  orderComponents?: boolean;
  /** Container this node is laid out inside, for grouped children. */
  parentId?: string;
  /** Flow direction for this node's own children, when it is a container. */
  direction?: "right" | "down";
};
export type LayoutEdge = { id: string; source: string; target: string };
export type LayoutPosition = { x: number; y: number };
/** Containers report the size ELK computed for their contents. */
export type LayoutSize = { width: number; height: number };
export type LayoutResult = {
  positions: Map<string, LayoutPosition>;
  sizes: Map<string, LayoutSize>;
  /** Absolute canvas coordinates of ELK orthogonal edge routes. */
  routes: Map<string, LayoutPosition[]>;
};

const elk = new ELK();

const ELK_DIRECTION = { right: "RIGHT", down: "DOWN" } as const;

type ElkEdge = {
  id: string;
  sources: string[];
  targets: string[];
  sections?: { id: string; startPoint: LayoutPosition; endPoint: LayoutPosition; bendPoints?: LayoutPosition[] }[];
};

type ElkNode = {
  id: string;
  width?: number;
  height?: number;
  layoutOptions?: Record<string, string>;
  children?: ElkNode[];
  edges?: ElkEdge[];
};

export async function layoutGraph(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  options: { orderComponents?: boolean } = {},
): Promise<LayoutResult> {
  const preserveOrder = nodes.some(node => node.layoutOrder != null);
  if (preserveOrder) {
    nodes = [...nodes].sort((a, b) => (a.layoutOrder ?? 0) - (b.layoutOrder ?? 0) || a.id.localeCompare(b.id));
  }
  const ordering: Record<string, string> = preserveOrder ? {
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    "elk.layered.crossingMinimization.forceNodeModelOrder": "true",
  } : {};
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
  const parentIds = new Map(nodes.map((node) => [node.id, node.parentId]));
  for (const node of nodes) {
    const ancestors = new Set<string>([node.id]);
    let parentId = node.parentId;
    while (parentId !== undefined) {
      if (ancestors.has(parentId)) throw new Error(`SGC_LAYOUT_PARENT_CYCLE: ${node.id}`);
      ancestors.add(parentId);
      parentId = parentIds.get(parentId);
    }
    if (node.parentId !== undefined && !ids.has(node.parentId)) {
      throw new Error(`SGC_LAYOUT_PARENT_MISSING: ${node.id}`);
    }
    if (node.parentId === node.id) {
      throw new Error(`SGC_LAYOUT_PARENT_CYCLE: ${node.id}`);
    }
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

  const built = new Map<string, ElkNode>();
  for (const node of nodes) {
    // Only explicitly ranked peers participate in forced model ordering.
    // Giving every descendant an order pushes long direct edges outside the
    // intervening layer instead of letting ELK use the space between nodes.
    const elkNode: ElkNode = { id: node.id, width: node.width, height: node.height,
      layoutOptions: node.layoutOrder == null ? {
        "elk.layered.considerModelOrder.noModelOrder": "true",
      } : {},
    };
    if (node.direction) {
      // A container carries its own algorithm and direction, which is what turns
      // a wide sibling band into a compact nested tree.
      elkNode.layoutOptions = {
        ...elkNode.layoutOptions,
        "elk.algorithm": "layered",
        ...(node.orderComponents ? {"elk.layered.considerModelOrder.components":"FORCE_MODEL_ORDER"} : {}),
        ...ordering,
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.layered.mergeEdges": "false",
        "elk.spacing.edgeEdge": "12",
        "elk.spacing.edgeNode": "16",
        "elk.layered.spacing.edgeEdgeBetweenLayers": "12",
        "elk.layered.spacing.edgeNodeBetweenLayers": "16",
        "elk.separateConnectedComponents": "true",
        "elk.spacing.componentComponent": "32",
        "elk.direction": ELK_DIRECTION[node.direction],
        "elk.spacing.nodeNode": "16",
        "elk.layered.spacing.nodeNodeBetweenLayers": "40",
        "elk.padding": "[top=36,left=16,bottom=16,right=16]",
      };
      elkNode.children = [];
    }
    built.set(node.id, elkNode);
  }
  const roots: ElkNode[] = [];
  for (const node of nodes) {
    const elkNode = built.get(node.id)!;
    const parent = node.parentId ? built.get(node.parentId) : undefined;
    if (!parent) {
      roots.push(elkNode);
      continue;
    }
    // A container sizes itself from its contents, so the declared size becomes a
    // minimum rather than a fixed box.
    (parent.children ??= []).push(elkNode);
    delete parent.width;
    delete parent.height;
  }

  // Internal edges belong to their container. Root-level edges referring to
  // nested members are unsupported by SEPARATE_CHILDREN; use ancestor proxies
  // for placement and let the renderer route those boundary connections.
  const rootEdges: ElkEdge[] = [];
  const proxyIds = new Set<string>();
  const rootOf = (id: string): string => {
    let parent = parentIds.get(id);
    while (parent) { id = parent; parent = parentIds.get(id); }
    return id;
  };
  for (const edge of edges) {
    const parent = parentIds.get(edge.source);
    if (parent === parentIds.get(edge.target)) {
      const routed = { id: edge.id, sources: [edge.source], targets: [edge.target] };
      if (parent) (built.get(parent)!.edges ??= []).push(routed);
      else rootEdges.push(routed);
    } else {
      const source = rootOf(edge.source);
      const target = rootOf(edge.target);
      if (source !== target) {
        rootEdges.push({ id: edge.id, sources: [source], targets: [target] });
        proxyIds.add(edge.id);
      }
    }
  }

  const result = await elk.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      ...(options.orderComponents ? {"elk.layered.considerModelOrder.components":"FORCE_MODEL_ORDER"} : {}),
        ...ordering,
      "elk.direction": "DOWN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": "48",
      "elk.layered.spacing.nodeNodeBetweenLayers": "90",
      // SEPARATE_CHILDREN, not INCLUDE_CHILDREN: the latter flattens the whole
      // hierarchy into one pass and overrides each container's own direction,
      // which is the entire point of grouping.
      "elk.hierarchyHandling": "SEPARATE_CHILDREN",
    },
    children: roots,
    edges: rootEdges,
  });

  const positions = new Map<string, LayoutPosition>();
  const sizes = new Map<string, LayoutSize>();
  const routes = new Map<string, LayoutPosition[]>();
  const collectEdges = (edges: ElkEdge[] | undefined, x: number, y: number) => {
    for (const edge of edges ?? []) {
      const section = edge.sections?.[0];
      if (!section || proxyIds.has(edge.id)) continue;
      routes.set(edge.id, [section.startPoint, ...(section.bendPoints ?? []), section.endPoint]
        .map((point) => ({ x: point.x + x, y: point.y + y })));
    }
  };
  // ELK reports child coordinates relative to their container, which is exactly
  // what React Flow expects from a node with a parent, so no rebasing is needed.
  const walk = (children: readonly ElkNode[] | undefined, x = 0, y = 0) => {
    for (const child of children ?? []) {
      const placed = child as ElkNode & { x?: number; y?: number };
      positions.set(child.id, { x: placed.x ?? 0, y: placed.y ?? 0 });
      if (child.width !== undefined && child.height !== undefined) {
        sizes.set(child.id, { width: child.width, height: child.height });
      }
      const childX = x + (placed.x ?? 0);
      const childY = y + (placed.y ?? 0);
      collectEdges(child.edges, childX, childY);
      walk(child.children, childX, childY);
    }
  };
  collectEdges(result.edges as ElkEdge[] | undefined, 0, 0);
  walk(result.children as ElkNode[] | undefined);
  return { positions, sizes, routes };
}
