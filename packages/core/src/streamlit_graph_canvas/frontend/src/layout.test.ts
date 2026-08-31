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
});
