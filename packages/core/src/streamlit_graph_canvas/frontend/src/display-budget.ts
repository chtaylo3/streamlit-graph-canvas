import type { GroupPlan, GroupTopologyNode, GroupTopologyEdge } from "./child-groups";

/** Budget the resolved scene, never the hidden collection membership. */
export function applyDisplayBudget(
  nodes: readonly GroupTopologyNode[], edges: readonly GroupTopologyEdge[],
  plan: GroupPlan, limit: number, anchor?: string | null,
): GroupPlan & { renderedElements: number; omittedNodes: number; omittedCollections: number } {
  const visible = nodes.filter(n=>!plan.hiddenNodeIds.has(n.id));
  const eligible = new Set(visible.map(n=>n.id));
  const adjacency = new Map<string, GroupTopologyEdge[]>();
  const parents = new Map<string, string[]>();
  for (const e of edges) {
    if (plan.hiddenEdgeIds.has(e.id) || !eligible.has(e.source) || !eligible.has(e.target)) continue;
    const incident=adjacency.get(e.source)??[];incident.push(e);adjacency.set(e.source,incident);
    if (e.source!==e.target) {
      const incoming=adjacency.get(e.target)??[];incoming.push(e);adjacency.set(e.target,incoming);
    }
    const predecessors=parents.get(e.target)??[];predecessors.push(e.source);parents.set(e.target,predecessors);
  }
  // Preserve the focused node and its navigation context before spending space
  // on an expanded collection. Walk ancestors iteratively to tolerate cycles.
  const priority: string[] = anchor && eligible.has(anchor) ? [anchor] : [];
  const seen = new Set(priority);
  for (let i=0;i<priority.length;i++) for (const id of parents.get(priority[i])??[]) {
    if (!seen.has(id)) {seen.add(id);priority.push(id);}
  }
  const anchorType=nodes.find(n=>n.id===anchor)?.type;
  const anchorParents=new Set(anchor ? parents.get(anchor)??[] : []);
  const siblings=new Set(visible.filter(n=>n.id!==anchor && n.type===anchorType &&
    (parents.get(n.id)??[]).some(id=>anchorParents.has(id))).map(n=>n.id));
  for (const n of visible) if (!plan.containerOf.has(n.id) && !siblings.has(n.id) && !seen.has(n.id)) {seen.add(n.id);priority.push(n.id);}
  for (const n of visible) if (!siblings.has(n.id) && !seen.has(n.id)) {seen.add(n.id);priority.push(n.id);}
  for (const n of visible) if (!seen.has(n.id)) {seen.add(n.id);priority.push(n.id);}
  const selected = new Set<string>(), collections = new Set<string>();
  let used=0;
  let pending=priority;
  while (pending.length) {
    const deferred: string[]=[];
    let progress=false;
    for (const id of pending) {
      const owner=plan.containerOf.get(id);
      if (owner && !collections.has(owner)) {deferred.push(id);continue;}
      const cost=1+(adjacency.get(id)??[]).filter(e=>
        (e.source===id && e.target===id) || selected.has(e.source===id?e.target:e.source)).length;
      if (used+cost>limit) continue;
      selected.add(id);used+=cost;progress=true;
      // Each visible collection is one node and one edge from its owner,
      // whether collapsed or expanded. Original membership edges are replaced.
      for (const group of plan.byParent.get(id)??[]) if (used+2<=limit) {
        collections.add(group.id);used+=2;
      }
    }
    if (!progress) break;
    pending=deferred;
  }
  const hiddenNodeIds=new Set(nodes.filter(n=>!selected.has(n.id)).map(n=>n.id));
  const groups=plan.groups.filter(g=>collections.has(g.id)).map(g=>({
    ...g, renderedMemberCount:g.memberIds.filter(id=>selected.has(id)).length,
  }));
  const byParent=new Map<string, typeof groups>();
  for (const g of groups) byParent.set(g.parentId,[...(byParent.get(g.parentId)??[]),g]);
  const containerOf=new Map([...plan.containerOf].filter(([id,owner])=>selected.has(id)&&collections.has(owner)));
  return {...plan,groups,byParent,containerOf,hiddenNodeIds,renderedElements:used,
    omittedNodes:visible.length-selected.size,omittedCollections:plan.groups.length-groups.length};
}
