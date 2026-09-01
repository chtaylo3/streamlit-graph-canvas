"""Optional adapters kept outside the core dependency set."""

from __future__ import annotations

from typing import Any

from .model import Edge, GraphData, Node


def from_networkx(graph: Any) -> GraphData:
    """Convert a directed NetworkX graph while preserving multigraph keys."""

    if not graph.is_directed():
        raise ValueError("Only directed NetworkX graphs are supported.")
    nodes: list[Node] = []
    for node_id, original in graph.nodes(data=True):
        data = dict(original)
        node_type = (
            data.pop("type") if "type" in data else data.pop("node_type", "default")
        )
        label = data.pop("label") if "label" in data else data.pop("name", node_id)
        nodes.append(
            Node(
                id=str(node_id),
                type=str(node_type),
                label=str(label),
                data=data,
            )
        )
    edges: list[Edge] = []
    if graph.is_multigraph():
        iterator = graph.edges(keys=True, data=True)
        records = (
            (source, target, key, data) for source, target, key, data in iterator
        )
    else:
        iterator = graph.edges(data=True)
        records = ((source, target, None, data) for source, target, data in iterator)
    for index, (source, target, key, original) in enumerate(records):
        data = dict(original)
        edge_id = str(data.pop("id", key if key is not None else f"edge-{index}"))
        edges.append(
            Edge(
                id=edge_id,
                source=str(source),
                target=str(target),
                type=str(
                    data.pop("type")
                    if "type" in data
                    else data.pop("edge_type", "default")
                ),
                source_port=data.pop("source_port", None),
                target_port=data.pop("target_port", None),
                label=data.pop("label", None),
                data=data,
            )
        )
    return GraphData(tuple(nodes), tuple(edges))
