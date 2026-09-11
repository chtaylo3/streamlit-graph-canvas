"""Optional graph context selection, independent of application UI and NetworkX."""

import math
from dataclasses import replace

from .model import Edge, GraphData


def add_sibling_context(
    visible: GraphData,
    available: GraphData,
    anchor_id: str,
    *,
    enabled: bool = False,
    opacity: float = 0.2,
    max_elements: int = 700,
    relationship_types: frozenset[str] | None = None,
) -> GraphData:
    """Append same-type siblings and their parent links within the remaining budget.

    Parents must already be visible. Existing nodes and edges take priority.
    Peers receive stable layout-order hints. Siblings are never expanded and
    remain selectable. Budget counts nodes plus edges, including parallel edges.
    Explicit opacity overrides legacy dimming. The caller chooses the anchor
    (for example, the repository containing the selected manifest).
    """
    if not enabled:
        return visible
    if (
        isinstance(opacity, bool)
        or not isinstance(opacity, (int, float))
        or not math.isfinite(opacity)
        or not 0 <= opacity <= 1
    ):
        raise ValueError("opacity must be a finite number between 0 and 1")
    if (
        isinstance(max_elements, bool)
        or not isinstance(max_elements, int)
        or max_elements < 1
    ):
        raise ValueError("max_elements must be a positive integer")
    if len(visible.nodes) + len(visible.edges) > max_elements:
        raise ValueError("visible graph already exceeds max_elements")
    nodes = {n.id: n for n in available.nodes}
    shown = {n.id for n in visible.nodes}
    if anchor_id not in nodes or anchor_id not in shown:
        return visible
    parent_types = {
        (e.source, e.type)
        for e in available.edges
        if e.target == anchor_id
        and e.source in shown
        and e.source != anchor_id
        and (relationship_types is None or e.type in relationship_types)
    }
    links: dict[str, list[Edge]] = {}
    for edge in available.edges:
        node = nodes.get(edge.target)
        if (
            (edge.source, edge.type) in parent_types
            and node is not None
            and node.id not in shown
            and node.type == nodes[anchor_id].type
        ):
            links.setdefault(node.id, []).append(edge)
    added_nodes = list(visible.nodes)
    added_edges = list(visible.edges)
    used_edges = {e.id for e in visible.edges}
    for node_id in sorted(links, key=lambda n: (nodes[n].label.casefold(), n)):
        edges = links[node_id]
        if any(e.id in used_edges for e in edges):
            raise ValueError(
                "available and visible graphs must use consistent edge IDs"
            )
        if len(added_nodes) + len(added_edges) + 1 + len(edges) > max_elements:
            continue
        added_nodes.append(replace(nodes[node_id], opacity=opacity))
        added_edges.extend(replace(e, opacity=opacity) for e in edges)
        used_edges.update(e.id for e in edges)
    # Rank every peer from the available graph, including the focused node.
    # Focus/opacity changes must not change the peer's ordering hint.
    peers = {
        e.target
        for e in available.edges
        if (e.source, e.type) in parent_types
        and e.target in nodes
        and nodes[e.target].type == nodes[anchor_id].type
    }
    order = {
        n: i
        for i, n in enumerate(
            sorted(peers, key=lambda n: (nodes[n].label.casefold(), n))
        )
    }
    return GraphData(
        tuple(
            replace(n, layout_order=order[n.id]) if n.id in order else n
            for n in added_nodes
        ),
        tuple(added_edges),
    )
