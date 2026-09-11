import { describe, expect, it } from "vitest";
import { layoutGraph } from "./layout";

describe("ELK layered layout", () => {
  it("places a target below its source", async () => {
    const { positions } = await layoutGraph(
      [
        { id: "source", width: 180, height: 92 },
        { id: "target", width: 180, height: 92 },
      ],
      [{ id: "edge", source: "source", target: "target" }],
    );

    expect(positions.get("target")!.y).toBeGreaterThan(
      positions.get("source")!.y,
    );
  });

  it("accepts parallel edges and self-loops", async () => {
    const { positions } = await layoutGraph(
      [
        { id: "a", width: 180, height: 92 },
        { id: "b", width: 180, height: 92 },
      ],
      [
        { id: "first", source: "a", target: "b" },
        { id: "second", source: "a", target: "b" },
        { id: "loop", source: "b", target: "b" },
      ],
    );

    expect([...positions]).toHaveLength(2);
  });

  it("is repeatable and keeps disconnected nodes from overlapping", async () => {
    const nodes = [
      { id: "a", width: 180, height: 92 },
      { id: "b", width: 120, height: 60 },
      { id: "c", width: 90, height: 90 },
    ];
    const { positions: first } = await layoutGraph(nodes, []);
    const { positions: second } = await layoutGraph(nodes, []);
    expect([...second]).toEqual([...first]);
    const boxes = nodes.map((node) => ({ ...node, ...first.get(node.id)! }));
    for (let left = 0; left < boxes.length; left += 1) {
      for (let right = left + 1; right < boxes.length; right += 1) {
        const a = boxes[left];
        const b = boxes[right];
        const overlaps =
          a.x < b.x + b.width &&
          a.x + a.width > b.x &&
          a.y < b.y + b.height &&
          a.y + a.height > b.y;
        expect(overlaps).toBe(false);
      }
    }
  });

  it("lays a container's members out inside it, positioned relative to it", async () => {
    const { positions, sizes } = await layoutGraph(
      [
        { id: "owner", width: 180, height: 92 },
        { id: "group", width: 180, height: 92, direction: "right" },
        { id: "one", width: 120, height: 48, parentId: "group" },
        { id: "two", width: 120, height: 48, parentId: "group" },
        { id: "three", width: 120, height: 48, parentId: "group" },
      ],
      [{ id: "owner-group", source: "owner", target: "group" }],
    );

    // React Flow expects child coordinates relative to the parent, which is what
    // ELK already reports, so members must not carry the container's offset.
    // A container sizes itself from its contents rather than its declared box.
    const size = sizes.get("group")!;
    expect(size.width).toBeGreaterThan(120);
    expect(size.height).toBeGreaterThan(48);
    for (const id of ["one", "two", "three"]) {
      const member = positions.get(id)!;
      expect(member.x).toBeGreaterThanOrEqual(0);
      expect(member.y).toBeGreaterThanOrEqual(0);
      expect(member.x).toBeLessThan(size.width);
      expect(member.y).toBeLessThan(size.height);
    }
  });

  it("flows a container's members rightward when asked", async () => {
    const { positions } = await layoutGraph(
      [
        { id: "group", width: 100, height: 50, direction: "right" },
        { id: "a", width: 100, height: 50, parentId: "group" },
        { id: "b", width: 100, height: 50, parentId: "group" },
      ],
      [{ id: "ab", source: "a", target: "b" }],
    );
    expect(positions.get("b")!.x).toBeGreaterThan(positions.get("a")!.x);
  });

  it("rejects a member whose container does not exist", async () => {
    await expect(
      layoutGraph([{ id: "a", width: 10, height: 10, parentId: "missing" }], []),
    ).rejects.toThrow("SGC_LAYOUT_PARENT_MISSING");
  });

  it("rejects a node that contains itself", async () => {
    await expect(
      layoutGraph([{ id: "a", width: 10, height: 10, parentId: "a" }], []),
    ).rejects.toThrow("SGC_LAYOUT_PARENT_CYCLE");
  });

  it("lays out a cycle with finite coordinates", async () => {
    const { positions } = await layoutGraph(
      [
        { id: "a", width: 100, height: 50 },
        { id: "b", width: 100, height: 50 },
        { id: "c", width: 100, height: 50 },
      ],
      [
        { id: "ab", source: "a", target: "b" },
        { id: "bc", source: "b", target: "c" },
        { id: "ca", source: "c", target: "a" },
      ],
    );
    expect(
      [...positions.values()].every(
        ({ x, y }) => Number.isFinite(x) && Number.isFinite(y),
      ),
    ).toBe(true);
  });

  it.each([
    [[{ id: "a", width: 0, height: 20 }], []],
    [
      [
        { id: "a", width: 20, height: 20 },
        { id: "a", width: 20, height: 20 },
      ],
      [],
    ],
    [
      [{ id: "a", width: 20, height: 20 }],
      [{ id: "bad", source: "a", target: "missing" }],
    ],
  ])("rejects malformed layout input", async (nodes, edges) => {
    await expect(layoutGraph(nodes, edges)).rejects.toThrow(/SGC_LAYOUT_/);
  });
});

describe("collection routing", () => {
  it("routes internal edges orthogonally in absolute coordinates around nodes", async () => {
    const nodes = [
      { id: "group", width: 100, height: 50, direction: "right" as const },
      ...["a", "b", "c", "d"].map((id) => ({ id, width: 100, height: 50, parentId: "group" })),
    ];
    const edges = [
      { id: "ab", source: "a", target: "b" },
      { id: "ac", source: "a", target: "c" },
      { id: "bd", source: "b", target: "d" },
      { id: "cd", source: "c", target: "d" },
      { id: "da", source: "d", target: "a" },
    ];
    const result = await layoutGraph(nodes, edges);
    const offset = result.positions.get("group")!;
    expect(result.routes.size).toBe(edges.length);
    for (const route of result.routes.values()) {
      for (let i = 1; i < route.length; i++) {
        const a = route[i - 1], b = route[i];
        expect(a.x === b.x || a.y === b.y).toBe(true);
        for (const node of nodes.slice(1)) {
          const p = result.positions.get(node.id)!;
          const x = p.x + offset.x, y = p.y + offset.y;
          const intersects = a.x === b.x
            ? a.x > x && a.x < x + node.width && Math.max(a.y, b.y) > y && Math.min(a.y, b.y) < y + node.height
            : a.y > y && a.y < y + node.height && Math.max(a.x, b.x) > x && Math.min(a.x, b.x) < x + node.width;
          expect(intersects).toBe(false);
        }
      }
    }
    const segments = [...result.routes.entries()].flatMap(([id, route]) =>
      route.slice(1).map((end, i) => ({ id, start: route[i], end })));
    for (let i = 0; i < segments.length; i++) {
      for (const b of segments.slice(i + 1)) {
        const a = segments[i];
        if (a.id === b.id) continue;
        const vertical = a.start.x === a.end.x && b.start.x === b.end.x && a.start.x === b.start.x;
        const horizontal = a.start.y === a.end.y && b.start.y === b.end.y && a.start.y === b.start.y;
        const axis = vertical ? "y" : "x";
        if (vertical || horizontal) {
          const overlap = Math.min(Math.max(a.start[axis], a.end[axis]), Math.max(b.start[axis], b.end[axis]))
            - Math.max(Math.min(a.start[axis], a.end[axis]), Math.min(b.start[axis], b.end[axis]));
          expect(overlap).toBeLessThanOrEqual(0);
        }
      }
    }
    expect((await layoutGraph(nodes, edges)).routes).toEqual(result.routes);
  });

  it("supports boundary connections without asking ELK to flatten container directions", async () => {
    const result = await layoutGraph([
      { id: "outside", width: 100, height: 50 },
      { id: "group", width: 100, height: 50, direction: "right" },
      { id: "a", width: 100, height: 50, parentId: "group" },
      { id: "b", width: 100, height: 50, parentId: "group" },
    ], [{ id: "in", source: "outside", target: "a" }, { id: "ab", source: "a", target: "b" }]);
    expect(result.positions.get("b")!.x).toBeGreaterThan(result.positions.get("a")!.x);
    expect(result.routes.has("ab")).toBe(true);
    expect(result.routes.has("in")).toBe(false); // explicit renderer fallback
  });

  it("rejects indirect parent cycles", async () => {
    await expect(layoutGraph([
      { id: "a", width: 10, height: 10, parentId: "b" },
      { id: "b", width: 10, height: 10, parentId: "a" },
    ], [])).rejects.toThrow("SGC_LAYOUT_PARENT_CYCLE");
  });
});

it("keeps ordered peers in the same relative positions when another peer gains children", async () => {
  const peers = ["a", "b", "c"].map((id, layoutOrder) => ({ id, width: 210, height: 96, layoutOrder }));
  const make = async (focus: string) => layoutGraph(
    [{ id: "parent", width: 210, height: 96 }, ...[...peers].sort((a,b) => Number(b.id === focus) - Number(a.id === focus)),
      ...Array.from({ length: focus === "a" ? 3 : 20 }, (_, i) => i).map(i => ({ id: `child-${i}`, width: 210, height: 96 }))],
    [...peers.map(n => ({ id: `parent-${n.id}`, source: "parent", target: n.id })),
      ...Array.from({ length: focus === "a" ? 3 : 20 }, (_, i) => i).map(i => ({ id: `${focus}-${i}`, source: focus, target: `child-${i}` }))],
  );
  const a = await make("a"), c = await make("c");
  const order = (result: Awaited<ReturnType<typeof layoutGraph>>) => [...peers].sort((a,b) => result.positions.get(a.id)!.x - result.positions.get(b.id)!.x).map(n => n.id);
  expect(order(a)).toEqual(["a", "b", "c"]);
  expect(order(c)).toEqual(order(a));
});

it("routes a direct dependency through the gap while preserving manifest sibling order", async () => {
  // The IDs deliberately sort requests after both packages in the preceding
  // layer, matching the pypi-core check_requirements regression.
  const ids = {
    account: "7098", repo: "c015", manifest: "2dc0", pygithub: "49ee",
    unidiff: "4be2", requests: "ec75",
  };
  const siblings = ["5940", ids.manifest, "7173", "3d7b", "a3eb", "4679"];
  const nodes = Object.values(ids).filter(id=>!siblings.includes(id)).map(id=>({id,width:210,height:96}));
  const edges = [
    {id:"owns",source:ids.account,target:ids.repo},
    ...siblings.map(id=>({id:"contains-"+id,source:ids.repo,target:id})),
    ...[ids.pygithub,ids.requests,ids.unidiff].map(id=>({id:"direct-"+id,source:ids.manifest,target:id})),
    {id:"transitive",source:ids.pygithub,target:ids.requests},
  ];
  const result = await layoutGraph([
    ...nodes,...siblings.map((id,layoutOrder)=>({id,width:210,height:96,layoutOrder})),
  ],edges);
  expect([...siblings].sort((a,b)=>result.positions.get(a)!.x-result.positions.get(b)!.x)).toEqual(siblings);
  const packages=[ids.pygithub,ids.unidiff].map(id=>result.positions.get(id)!).sort((a,b)=>a.x-b.x);
  const route=result.routes.get("direct-"+ids.requests)!;
  const middleY=packages[0].y+48;
  const throughLayer=route.slice(1).filter((end,i)=>end.x===route[i].x && Math.min(end.y,route[i].y)<middleY && Math.max(end.y,route[i].y)>middleY);
  expect(throughLayer).toHaveLength(1);
  expect(throughLayer[0].x).toBeGreaterThan(packages[0].x+210);
  expect(throughLayer[0].x).toBeLessThan(packages[1].x);
});

it("packs explicitly ranked disconnected collection members in reading order",async()=>{
  const result=await layoutGraph([
    {id:"group",width:100,height:50,direction:"right",orderComponents:true},
    ...["a","b","c","d"].map((id,i)=>({id,width:100,height:50,parentId:"group",layoutOrder:id==="d"?0:i+1})),
  ],[]);
  const order=["a","b","c","d"].sort((a,b)=>result.positions.get(a)!.y-result.positions.get(b)!.y||result.positions.get(a)!.x-result.positions.get(b)!.x);
  expect(order[0]).toBe("d");
});
