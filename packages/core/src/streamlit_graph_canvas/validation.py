"""Strict schema and graph preflight validation."""

from __future__ import annotations

from collections.abc import Iterable

from .errors import Diagnostic, ValidationError
from .model import AnyNodeType, EdgeType, GraphData, GraphSchema


def _fail(code: str, message: str, action: str, subject: str | None = None) -> None:
    raise ValidationError(Diagnostic(code, message, action, subject))


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _validate_endpoint_types(edge_type: EdgeType, schema: GraphSchema) -> None:
    for role, allowed in (
        ("source", edge_type.source_types),
        ("target", edge_type.target_types),
    ):
        if isinstance(allowed, AnyNodeType):
            continue
        unknown = allowed - schema.node_types.keys()
        if unknown:
            _fail(
                "SGC_SCHEMA_EDGE_ENDPOINT_TYPE",
                f"Edge type declares unknown {role} node types: {sorted(unknown)}.",
                "Declare those node types or remove them from the edge type.",
                edge_type.name,
            )


def validate(schema: GraphSchema, graph: GraphData, *, max_elements: int = 700) -> None:
    """Validate a graph completely before it crosses the component boundary."""

    if max_elements <= 0:
        _fail(
            "SGC_BUDGET_INVALID",
            "max_elements must be positive.",
            "Pass a positive integer element budget.",
        )
    if len(graph.nodes) + len(graph.edges) > max_elements:
        _fail(
            "SGC_BUDGET_EXCEEDED",
            f"Graph has {len(graph.nodes)} nodes and {len(graph.edges)} edges, "
            f"exceeding the {max_elements}-element budget.",
            "Window the graph in the host application or increase max_elements.",
        )
    for key, declaration in schema.node_types.items():
        if not key or key != declaration.name:
            _fail(
                "SGC_SCHEMA_NODE_TYPE_NAME",
                "Node type mapping keys must be non-empty and match their names.",
                "Use the same stable name for the mapping key and declaration.",
                key,
            )
        if declaration.style.width <= 0 or declaration.style.height <= 0:
            _fail(
                "SGC_SCHEMA_NODE_GEOMETRY",
                "Node type dimensions must be positive.",
                "Set positive width and height values.",
                key,
            )
        names = [port.name for port in declaration.ports]
        if duplicates := _duplicates(names):
            _fail(
                "SGC_SCHEMA_DUPLICATE_PORT",
                f"Node type has duplicate ports: {sorted(duplicates)}.",
                "Give every port on the node type a unique name.",
                key,
            )
    for key, declaration in schema.edge_types.items():
        if not key or key != declaration.name:
            _fail(
                "SGC_SCHEMA_EDGE_TYPE_NAME",
                "Edge type mapping keys must be non-empty and match their names.",
                "Use the same stable name for the mapping key and declaration.",
                key,
            )
        _validate_endpoint_types(declaration, schema)

    node_ids = [node.id for node in graph.nodes]
    if duplicates := _duplicates(node_ids):
        _fail(
            "SGC_GRAPH_DUPLICATE_NODE",
            f"Graph has duplicate node IDs: {sorted(duplicates)}.",
            "Assign every node a stable unique string ID.",
        )
    edge_ids = [edge.id for edge in graph.edges]
    if duplicates := _duplicates(edge_ids):
        _fail(
            "SGC_GRAPH_DUPLICATE_EDGE",
            f"Graph has duplicate edge IDs: {sorted(duplicates)}.",
            "Assign every edge a stable unique string ID.",
        )
    nodes = {node.id: node for node in graph.nodes}
    for node in graph.nodes:
        if not node.id:
            _fail(
                "SGC_GRAPH_NODE_ID",
                "Node IDs must be non-empty strings.",
                "Assign the node a stable non-empty ID.",
            )
        if node.type not in schema.node_types:
            _fail(
                "SGC_GRAPH_NODE_TYPE",
                f"Node uses undeclared type {node.type!r}.",
                "Declare the node type in GraphSchema.",
                node.id,
            )
        if (node.width is not None and node.width <= 0) or (
            node.height is not None and node.height <= 0
        ):
            _fail(
                "SGC_GRAPH_NODE_GEOMETRY",
                "Explicit node dimensions must be positive.",
                "Remove the override or pass a positive dimension.",
                node.id,
            )
    for edge in graph.edges:
        if not edge.id:
            _fail(
                "SGC_GRAPH_EDGE_ID",
                "Edge IDs must be non-empty strings.",
                "Assign the edge a stable non-empty ID.",
            )
        if edge.source not in nodes or edge.target not in nodes:
            _fail(
                "SGC_GRAPH_EDGE_ENDPOINT",
                f"Edge endpoints {edge.source!r} -> {edge.target!r} must exist.",
                "Add the missing nodes or remove the malformed edge.",
                edge.id,
            )
        if edge.type not in schema.edge_types:
            _fail(
                "SGC_GRAPH_EDGE_TYPE",
                f"Edge uses undeclared type {edge.type!r}.",
                "Declare the edge type in GraphSchema.",
                edge.id,
            )
        declaration = schema.edge_types[edge.type]
        source = nodes[edge.source]
        target = nodes[edge.target]
        if (
            not isinstance(declaration.source_types, AnyNodeType)
            and source.type not in declaration.source_types
        ):
            _fail(
                "SGC_GRAPH_EDGE_SOURCE_TYPE",
                f"Source node type {source.type!r} is not allowed.",
                "Use an allowed source type or update the edge declaration.",
                edge.id,
            )
        if (
            not isinstance(declaration.target_types, AnyNodeType)
            and target.type not in declaration.target_types
        ):
            _fail(
                "SGC_GRAPH_EDGE_TARGET_TYPE",
                f"Target node type {target.type!r} is not allowed.",
                "Use an allowed target type or update the edge declaration.",
                edge.id,
            )
        for node, port_name, role in (
            (source, edge.source_port, "source"),
            (target, edge.target_port, "target"),
        ):
            ports = {port.name for port in schema.node_types[node.type].ports}
            if port_name is not None and port_name not in ports:
                _fail(
                    "SGC_GRAPH_EDGE_PORT",
                    f"Edge references undeclared {role} port {port_name!r}.",
                    "Declare the port on the node type or correct the edge.",
                    edge.id,
                )
