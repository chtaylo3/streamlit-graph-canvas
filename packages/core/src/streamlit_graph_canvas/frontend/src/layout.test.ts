import { describe, expect, it } from "vitest";
import { layoutGraph } from "./layout";

describe("ELK layered layout", () => {
  it("places a target below its source", async () => {
    const positions = await layoutGraph(
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
    const positions = await layoutGraph(
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
    const first = await layoutGraph(nodes, []);
    const second = await layoutGraph(nodes, []);
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

  it("lays out a cycle with finite coordinates", async () => {
    const positions = await layoutGraph(
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
