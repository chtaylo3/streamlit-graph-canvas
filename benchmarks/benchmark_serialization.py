"""Record deterministic beta serialization measurements without a hard threshold."""

from __future__ import annotations

import json
import statistics
import time

from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    serialize_graph,
)


def main() -> None:
    nodes = tuple(Node(f"n{index}", "item", f"Node {index}") for index in range(350))
    edges = tuple(
        Edge(f"e{index}", f"n{index}", f"n{index + 1}", "link") for index in range(349)
    )
    graph = GraphData(nodes, edges)
    schema = GraphSchema({"item": NodeType("item")}, {"link": EdgeType("link")})
    durations: list[float] = []
    result = None
    for _ in range(10):
        started = time.perf_counter()
        result = serialize_graph(schema, graph)
        durations.append((time.perf_counter() - started) * 1_000)
    assert result is not None
    payload = json.dumps(result.envelope, separators=(",", ":")).encode()
    print(
        json.dumps(
            {
                "elements": 699,
                "iterations": len(durations),
                "median_ms": statistics.median(durations),
                "p95_ms": sorted(durations)[-1],
                "payload_bytes": len(payload),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
