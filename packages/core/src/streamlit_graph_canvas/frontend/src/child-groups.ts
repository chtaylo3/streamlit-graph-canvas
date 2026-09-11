/**
 * Collapse high fan-out children behind expandable group containers.
 *
 * A node with many children of one relationship flattens into a single very wide
 * band, because every child sits at the same depth. Grouping moves those children
 * into a container: collapsed it leaves the layout entirely, expanded it is laid
 * out as a nested subgraph with its own flow direction.
 *
 * This module is deliberately pure. It decides *what* is grouped; the layout and
 * the renderer decide how that looks.
 */

export type ChildGroupSpec = {
  edgeType: string;
  label: string;
  threshold: number;
  display?: "tree" | "collection" | "cutoff";
  direction: "right" | "down";
  collapsed: boolean;
};

export type GroupTopologyNode = { id: string; type: string };
export type GroupTopologyEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
};

export type ResolvedGroup = {
  id: string;
  parentId: string;
  edgeType: string;
  label: string;
  direction: "right" | "down";
  memberIds: string[];
  expanded: boolean;
  renderedMemberCount?: number;
};

export type GroupPlan = {
  groups: ResolvedGroup[];
  /** Members of collapsed groups that nothing else keeps on screen. */
  hiddenNodeIds: ReadonlySet<string>;
  /** Edges the group replaces, so they are not drawn twice. */
  hiddenEdgeIds: ReadonlySet<string>;
  /** Member -> container, for expanded groups only. */
  containerOf: ReadonlyMap<string, string>;
  /** Group id -> the group, for marker lookup on the owning node. */
  byParent: ReadonlyMap<string, ResolvedGroup[]>;
};

/** Namespaced so a synthetic container can never collide with a real node id. */
export const GROUP_ID_PREFIX = "sgc-group:";

export function groupId(parentId: string, edgeType: string): string {
  return `${GROUP_ID_PREFIX}${parentId}\u0000${edgeType}`;
}

export function isGroupId(id: string): boolean {
  return id.startsWith(GROUP_ID_PREFIX);
}

const EMPTY_PLAN: GroupPlan = {
  groups: [],
  hiddenNodeIds: new Set(),
  hiddenEdgeIds: new Set(),
  containerOf: new Map(),
  byParent: new Map(),
};

export function planChildGroups(
  nodes: readonly GroupTopologyNode[],
  edges: readonly GroupTopologyEdge[],
  specsByNodeType: Readonly<Record<string, readonly ChildGroupSpec[]>>,
  toggled: ReadonlySet<string>,
): GroupPlan {
  const declaring = new Map<string, readonly ChildGroupSpec[]>();
  for (const node of nodes) {
    const specs = specsByNodeType[node.type];
    if (specs && specs.length > 0) declaring.set(node.id, specs);
  }
  if (declaring.size === 0) return EMPTY_PLAN;

  // Candidate members per (owner, edge type), in topology order so the layout is
  // deterministic across reruns.
  const candidates = new Map<
    string,
    { spec: ChildGroupSpec; edges: GroupTopologyEdge[] }
  >();
  for (const edge of edges) {
    const specs = declaring.get(edge.source);
    if (!specs) continue;
    const spec = specs.find((item) => item.edgeType === edge.type);
    if (!spec) continue;
    const key = groupId(edge.source, edge.type);
    const existing = candidates.get(key);
    if (existing) existing.edges.push(edge);
    else candidates.set(key, { spec, edges: [edge] });
  }

  const groups: ResolvedGroup[] = [];
  const hiddenEdgeIds = new Set<string>();
  const containerOf = new Map<string, string>();

  for (const [id, { spec, edges: memberEdges }] of [...candidates].sort(
    ([a], [b]) => a.localeCompare(b),
  )) {
    // A group that would hold fewer children than its threshold is not worth the
    // indirection: drawing two nodes behind a marker costs more than it saves.
    const memberIds = [
      ...new Set(memberEdges.map((edge) => edge.target)),
    ].filter((id) => id !== memberEdges[0].source);
    if (spec.display === "tree" || memberIds.length === 0) continue;
    if (spec.display !== "collection" && memberIds.length < spec.threshold)
      continue;
    // `toggled` records groups the viewer flipped away from their declared
    // default, so one set expresses both "opened" and "closed" without the
    // renderer needing to know which default each group started from.
    const group: ResolvedGroup = {
      id,
      parentId: memberEdges[0].source,
      edgeType: spec.edgeType,
      label: spec.label || spec.edgeType,
      direction: spec.direction,
      memberIds,
      expanded: spec.collapsed ? toggled.has(id) : !toggled.has(id),
    };
    groups.push(group);
    for (const edge of memberEdges) {
      if (edge.source !== edge.target) hiddenEdgeIds.add(edge.id);
    }
  }

  if (groups.length === 0) return EMPTY_PLAN;

  // Visibility flows only from visible sources. Expanded descendants of a
  // collapsed owner cannot leak into the canvas, even when their toggle state
  // is retained for the next expansion.
  const visible = new Set(sourceAnchors(nodes, edges));
  const successors = new Map<string, string[]>();
  const append = (source: string, target: string) => {
    const targets = successors.get(source);
    if (targets) targets.push(target);
    else successors.set(source, [target]);
  };
  for (const group of groups) {
    if (group.expanded)
      for (const id of group.memberIds) append(group.parentId, id);
  }
  for (const edge of edges) {
    if (!hiddenEdgeIds.has(edge.id)) append(edge.source, edge.target);
  }
  const queue = [...visible];
  for (let index = 0; index < queue.length; index++) {
    for (const id of successors.get(queue[index]) ?? []) {
      if (!visible.has(id)) {
        visible.add(id);
        queue.push(id);
      }
    }
  }
  const hiddenNodeIds = new Set(
    nodes.filter((node) => !visible.has(node.id)).map((node) => node.id),
  );
  const visibleGroups = groups.filter((group) => visible.has(group.parentId));
  const memberships = new Map<string, string[]>();
  for (const group of visibleGroups) {
    if (!group.expanded) continue;
    for (const id of group.memberIds) {
      const owners = memberships.get(id) ?? [];
      owners.push(group.id);
      memberships.set(id, owners);
    }
  }
  for (const [id, owners] of memberships) {
    // Shared children stay at the root rather than arbitrarily belonging to the
    // last group. Expanded relationships to them remain visible.
    if (owners.length === 1) containerOf.set(id, owners[0]);
  }
  const groupLookup = new Map(visibleGroups.map((group) => [group.id, group]));
  for (const edge of edges) {
    const group = groupLookup.get(groupId(edge.source, edge.type));
    if (group?.expanded && !containerOf.has(edge.target))
      hiddenEdgeIds.delete(edge.id);
  }

  const byParent = new Map<string, ResolvedGroup[]>();
  for (const group of visibleGroups) {
    const existing = byParent.get(group.parentId);
    if (existing) existing.push(group);
    else byParent.set(group.parentId, [group]);
  }
  for (const list of byParent.values()) {
    list.sort((left, right) => left.edgeType.localeCompare(right.edgeType));
  }

  return {
    groups: visibleGroups,
    hiddenNodeIds,
    hiddenEdgeIds,
    containerOf,
    byParent,
  };
}

/** One stable anchor per source strongly connected component, including cycles.
 * Iterative Kosaraju avoids recursion depth limits on long dependency chains.
 */
function sourceAnchors(
  nodes: readonly GroupTopologyNode[],
  edges: readonly GroupTopologyEdge[],
): string[] {
  const forward = new Map(nodes.map((node) => [node.id, [] as string[]]));
  const reverse = new Map(nodes.map((node) => [node.id, [] as string[]]));
  for (const edge of edges) {
    forward.get(edge.source)?.push(edge.target);
    reverse.get(edge.target)?.push(edge.source);
  }
  const visited = new Set<string>();
  const order: string[] = [];
  for (const node of nodes) {
    const stack: [string, boolean][] = [[node.id, false]];
    while (stack.length) {
      const [id, exiting] = stack.pop()!;
      if (exiting) {
        order.push(id);
        continue;
      }
      if (visited.has(id)) continue;
      visited.add(id);
      stack.push([id, true]);
      for (const target of forward.get(id) ?? []) {
        if (!visited.has(target)) stack.push([target, false]);
      }
    }
  }
  const componentOf = new Map<string, number>();
  const anchors: string[] = [];
  for (const id of order.reverse()) {
    if (componentOf.has(id)) continue;
    const component = anchors.length;
    let anchor = id;
    const stack = [id];
    while (stack.length) {
      const current = stack.pop()!;
      if (componentOf.has(current)) continue;
      componentOf.set(current, component);
      if (current < anchor) anchor = current;
      for (const source of reverse.get(current) ?? []) stack.push(source);
    }
    anchors.push(anchor);
  }
  const incoming = new Set<number>();
  for (const edge of edges) {
    if (componentOf.get(edge.source) !== componentOf.get(edge.target)) {
      incoming.add(componentOf.get(edge.target)!);
    }
  }
  return anchors.filter((_, index) => !incoming.has(index));
}
