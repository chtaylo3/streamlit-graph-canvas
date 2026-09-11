import { describe, expect, it } from "vitest";
import { groupId, isGroupId, planChildGroups } from "./child-groups";
import type { ChildGroupSpec } from "./child-groups";

const RESOLVES: ChildGroupSpec = {
  edgeType: "resolves",
  label: "Resolved packages",
  threshold: 3,
  direction: "right",
  collapsed: true,
};

function fanOut(count: number, type = "resolves") {
  const nodes = [
    { id: "manifest", type: "manifest" },
    ...Array.from({ length: count }, (_, index) => ({
      id: `pkg-${index}`,
      type: "dependency",
    })),
  ];
  const edges = Array.from({ length: count }, (_, index) => ({
    id: `e-${index}`,
    source: "manifest",
    target: `pkg-${index}`,
    type,
  }));
  return { nodes, edges };
}

describe("child groups", () => {
  it("leaves a graph untouched when no node type declares a group", () => {
    const { nodes, edges } = fanOut(50);
    const plan = planChildGroups(nodes, edges, {}, new Set());
    expect(plan.groups).toHaveLength(0);
    expect(plan.hiddenNodeIds.size).toBe(0);
    expect(plan.hiddenEdgeIds.size).toBe(0);
  });

  it("collapses a fan-out and hides its members and edges", () => {
    const { nodes, edges } = fanOut(50);
    const plan = planChildGroups(
      nodes,
      edges,
      { manifest: [RESOLVES] },
      new Set(),
    );
    expect(plan.groups).toHaveLength(1);
    const group = plan.groups[0];
    expect(group.expanded).toBe(false);
    expect(group.memberIds).toHaveLength(50);
    expect(group.label).toBe("Resolved packages");
    expect(plan.hiddenNodeIds.size).toBe(50);
    expect(plan.hiddenEdgeIds.size).toBe(50);
    expect(plan.containerOf.size).toBe(0);
  });

  it("does not group a fan-out below the declared threshold", () => {
    const { nodes, edges } = fanOut(2);
    const plan = planChildGroups(nodes, edges, { manifest: [RESOLVES] }, new Set());
    expect(plan.groups).toHaveLength(0);
    expect(plan.hiddenNodeIds.size).toBe(0);
  });

  it("places members inside the container once toggled open", () => {
    const { nodes, edges } = fanOut(10);
    const id = groupId("manifest", "resolves");
    const plan = planChildGroups(
      nodes,
      edges,
      { manifest: [RESOLVES] },
      new Set([id]),
    );
    expect(plan.groups[0].expanded).toBe(true);
    expect(plan.hiddenNodeIds.size).toBe(0);
    expect(plan.containerOf.get("pkg-0")).toBe(id);
    expect(plan.containerOf.size).toBe(10);
  });

  it("treats the toggle set as a flip from the declared default", () => {
    const { nodes, edges } = fanOut(10);
    const openByDefault = { ...RESOLVES, collapsed: false };
    const id = groupId("manifest", "resolves");

    const untouched = planChildGroups(
      nodes, edges, { manifest: [openByDefault] }, new Set(),
    );
    expect(untouched.groups[0].expanded).toBe(true);

    const flipped = planChildGroups(
      nodes, edges, { manifest: [openByDefault] }, new Set([id]),
    );
    expect(flipped.groups[0].expanded).toBe(false);
  });

  it("keeps a collapsed member that another visible edge still points at", () => {
    const { nodes, edges } = fanOut(5);
    const plan = planChildGroups(
      [...nodes, { id: "other", type: "manifest" }],
      // "other" depends on pkg-0 directly, and that edge is not part of any group.
      [...edges, { id: "keep", source: "other", target: "pkg-0", type: "depends_on" }],
      { manifest: [RESOLVES] },
      new Set(),
    );
    expect(plan.hiddenNodeIds.has("pkg-0")).toBe(false);
    expect(plan.hiddenNodeIds.size).toBe(4);
  });

  it("hides members that only depend on each other", () => {
    // Members of one lock file routinely depend on one another. An edge whose
    // own source is hidden must not keep its target drawn, or the group leaks
    // stragglers and the view never looks collapsed.
    const { nodes, edges } = fanOut(20);
    const internal = [
      { id: "chain-1", source: "pkg-0", target: "pkg-1", type: "depends_on" },
      { id: "chain-2", source: "pkg-1", target: "pkg-2", type: "depends_on" },
      { id: "chain-3", source: "pkg-2", target: "pkg-3", type: "depends_on" },
    ];
    const plan = planChildGroups(
      nodes, [...edges, ...internal], { manifest: [RESOLVES] }, new Set(),
    );
    expect(plan.hiddenNodeIds.size).toBe(20);
  });

  it("still anchors a member reached from something visible", () => {
    const { nodes, edges } = fanOut(20);
    const plan = planChildGroups(
      [...nodes, { id: "outside", type: "dependency" }],
      [
        ...edges,
        // "outside" is never grouped, so anything it points at stays drawn.
        { id: "anchor", source: "outside", target: "pkg-7", type: "depends_on" },
        // pkg-7 in turn anchors pkg-8, transitively.
        { id: "chain", source: "pkg-7", target: "pkg-8", type: "depends_on" },
      ],
      { manifest: [RESOLVES] },
      new Set(),
    );
    expect(plan.hiddenNodeIds.has("pkg-7")).toBe(false);
    expect(plan.hiddenNodeIds.has("pkg-8")).toBe(false);
    expect(plan.hiddenNodeIds.size).toBe(18);
  });

  it("separates groups by edge type on the same owner", () => {
    const resolves = fanOut(20, "resolves");
    const depends = fanOut(20, "depends_on");
    const plan = planChildGroups(
      [...resolves.nodes, ...depends.nodes.slice(1).map((n) => ({ ...n, id: `d-${n.id}` }))],
      [
        ...resolves.edges,
        ...depends.edges.map((e) => ({ ...e, id: `d-${e.id}`, target: `d-${e.target}` })),
      ],
      {
        manifest: [
          RESOLVES,
          { ...RESOLVES, edgeType: "depends_on", label: "Direct dependencies" },
        ],
      },
      new Set(),
    );
    expect(plan.groups).toHaveLength(2);
    expect(plan.byParent.get("manifest")).toHaveLength(2);
    // Sorted by edge type so marker order is stable across reruns.
    expect(plan.byParent.get("manifest")!.map((g) => g.edgeType)).toEqual([
      "depends_on",
      "resolves",
    ]);
  });

  it("namespaces container ids so they cannot collide with real nodes", () => {
    const id = groupId("manifest", "resolves");
    expect(isGroupId(id)).toBe(true);
    expect(isGroupId("manifest")).toBe(false);
    expect(id).not.toBe(groupId("manifest", "depends_on"));
  });

  it("keeps member order stable so the layout does not churn", () => {
    const { nodes, edges } = fanOut(30);
    const first = planChildGroups(nodes, edges, { manifest: [RESOLVES] }, new Set());
    const second = planChildGroups(
      nodes, [...edges], { manifest: [RESOLVES] }, new Set(),
    );
    expect(second.groups[0].memberIds).toEqual(first.groups[0].memberIds);
  });
});

describe("display policy", () => {
  it.each([0, 1, 2, 3, 4])("evaluates cutoff at the boundary for %i children", (count) => {
    const { nodes, edges } = fanOut(count);
    for (const display of ["tree", "collection", "cutoff"] as const) {
      const plan = planChildGroups(nodes, edges, { manifest: [{ ...RESOLVES, display }] }, new Set());
      const grouped = count > 0 && (display === "collection" || (display === "cutoff" && count >= 3));
      expect(plan.groups.length).toBe(grouped ? 1 : 0);
      expect(plan.hiddenNodeIds.size).toBe(grouped ? count : 0);
    }
  });

  it("counts distinct children per category, not edges or total degree", () => {
    const { nodes, edges } = fanOut(3);
    edges[2].type = "depends_on";
    edges.push({ ...edges[0], id: "parallel" });
    const plan = planChildGroups(nodes, edges, { manifest: [RESOLVES, { ...RESOLVES, edgeType: "depends_on" }] }, new Set());
    expect(plan.groups).toHaveLength(0);
  });

  it("retains expansion choice when switching tree mode off and on", () => {
    const { nodes, edges } = fanOut(3);
    const toggled = new Set([groupId("manifest", "resolves")]);
    const tree = planChildGroups(nodes, edges, { manifest: [{ ...RESOLVES, display: "tree" }] }, toggled);
    expect(tree.hiddenNodeIds.size).toBe(0);
    const collection = planChildGroups(nodes, edges, { manifest: [{ ...RESOLVES, display: "collection" }] }, toggled);
    expect(collection.groups[0].expanded).toBe(true);
  });
});

it("hides expanded descendant groups when their owner is collapsed", () => {
  const nodes = ["root", "child", "grandchild"].map((id) => ({ id, type: "n" }));
  const edges = [{ id: "a", source: "root", target: "child", type: "resolves" },
    { id: "b", source: "child", target: "grandchild", type: "resolves" }];
  const plan = planChildGroups(nodes, edges, { n: [{ ...RESOLVES, threshold: 1 }] }, new Set([groupId("child", "resolves")]));
  expect([...plan.hiddenNodeIds].sort()).toEqual(["child", "grandchild"]);
  expect(plan.groups.map((g) => g.parentId)).toEqual(["root"]);
  expect(plan.containerOf.size).toBe(0);
});

it("keeps a shared child outside both expanded collections with its relationships", () => {
  const nodes = ["a", "b", "shared"].map((id) => ({ id, type: "n" }));
  const edges = ["a", "b"].map((id) => ({ id, source: id, target: "shared", type: "resolves" }));
  const plan = planChildGroups(nodes, edges, { n: [{ ...RESOLVES, threshold: 1, collapsed: false }] }, new Set());
  expect(plan.hiddenNodeIds.size).toBe(0);
  expect(plan.containerOf.has("shared")).toBe(false);
  expect(plan.hiddenEdgeIds.size).toBe(0);
});


it("anchors a rootless cycle upstream of a lexically earlier sink", () => {
  const nodes = ["0-sink", "a", "b"].map((id) => ({ id, type: "n" }));
  const edges = [["a", "b"], ["b", "a"], ["b", "0-sink"]].map(([source, target], i) => ({
    id: String(i), source, target, type: "resolves",
  }));
  const plan = planChildGroups(nodes, edges, { n: [{ ...RESOLVES, threshold: 1 }] }, new Set());
  expect(plan.groups.map((group) => group.parentId)).toEqual(["a"]);
  expect([...plan.hiddenNodeIds].sort()).toEqual(["0-sink", "b"]);
  const expanded = planChildGroups(nodes, edges, { n: [{ ...RESOLVES, threshold: 1, collapsed: false }] }, new Set());
  expect(expanded.hiddenNodeIds.size).toBe(0);
});

it("visits reversed deep-chain edges linearly before applying any display budget", () => {
  const count = 3000;
  let sourceReads = 0;
  const nodes = Array.from({length: count}, (_,i) => ({id: String(i), type: i ? "item" : "root"}));
  const edges = Array.from({length: count-1}, (_,i) => new Proxy({
    id: `e${i}`, source: String(i), target: String(i+1), type: i ? "link" : "resolves",
  }, {get(target, key) { if(key === "source") sourceReads++; return Reflect.get(target, key); }}));
  const specs = {root: [{...RESOLVES, threshold: 1, collapsed: false}]};
  const reversed = planChildGroups(nodes, [...edges].reverse(), specs, new Set());
  expect(reversed.hiddenNodeIds.size).toBe(0);
  expect(sourceReads).toBeLessThan(edges.length * 20);
  const forward = planChildGroups(nodes, edges, specs, new Set());
  expect(reversed).toEqual(forward);
});
