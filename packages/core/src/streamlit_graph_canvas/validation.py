"""Strict schema and graph preflight validation."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, NoReturn

from .contract import (
    MAX_COLLECTION_ITEMS,
    MAX_DATA_DEPTH,
    MAX_DATA_STRING_CHARS,
    MAX_DATA_VALUES,
)
from .errors import Diagnostic, ValidationError
from .json_budget import JsonBudget, JsonLimitError, bounded_json_size
from .model import BUILTIN_PALETTE, AnyNodeType, EdgeType, GraphData, GraphSchema

if TYPE_CHECKING:
    from .renderers import RendererRegistry


def _fail(code: str, message: str, action: str, subject: str | None = None) -> NoReturn:
    raise ValidationError(Diagnostic(code, message, action, subject))


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


_DATA_CODES = {
    "depth": "SGC_DATA_DEPTH",
    "integer": "SGC_DATA_INTEGER",
    "number": "SGC_DATA_NUMBER",
    "key": "SGC_DATA_KEY",
    "type": "SGC_DATA_TYPE",
    "string": "SGC_DATA_STRING_LIMIT",
    "collection": "SGC_DATA_COLLECTION_LIMIT",
    "values": "SGC_DATA_VALUES_LIMIT",
    "size": "SGC_DATA_SIZE",
}


def _data_error(error: JsonLimitError, *, subject: str) -> NoReturn:
    _fail(
        _DATA_CODES[error.kind],
        f"Graph data is outside the supported JSON budget: {error.detail}.",
        "Window, flatten, or summarize graph data before rendering.",
        subject,
    )


def _json_value(value: Any, *, subject: str, max_bytes: int = 2_000_000) -> None:
    try:
        bounded_json_size(
            value,
            max_bytes=max_bytes,
            max_depth=MAX_DATA_DEPTH,
            max_string_chars=MAX_DATA_STRING_CHARS,
            max_collection_items=MAX_COLLECTION_ITEMS,
            max_values=MAX_DATA_VALUES,
        )
    except JsonLimitError as error:
        _data_error(error, subject=subject)


def _validate_graph_data(graph: GraphData, *, max_data_bytes: int) -> None:
    budget = JsonBudget(
        max_data_bytes,
        MAX_DATA_DEPTH,
        MAX_DATA_STRING_CHARS,
        MAX_COLLECTION_ITEMS,
        MAX_DATA_VALUES,
    )
    try:
        budget.token('{"nodes":[')
        for index, node in enumerate(graph.nodes):
            if index:
                budget.token(",")
            budget.object_fields(
                (
                    ("id", node.id),
                    ("type", node.type),
                    ("label", node.label),
                    ("data", node.data),
                    ("badges", node.badges),
                ),
                depth=2,
            )
        budget.token('],"edges":[')
        for index, edge in enumerate(graph.edges):
            if index:
                budget.token(",")
            budget.object_fields(
                (
                    ("id", edge.id),
                    ("source", edge.source),
                    ("target", edge.target),
                    ("type", edge.type),
                    ("source_port", edge.source_port),
                    ("target_port", edge.target_port),
                    ("label", edge.label),
                    ("data", edge.data),
                ),
                depth=2,
            )
        budget.token("]}")
    except JsonLimitError as error:
        _data_error(error, subject="graph")


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


_COLOR_FUNCTION = re.compile(
    r"(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\([0-9a-zA-Z.,%+\-/ ]+\)"
)
_THEME_VARIABLE = re.compile(r"var\(--st-[a-z0-9-]+\)")
_COLOR_KEYWORD = re.compile(r"[a-zA-Z]+")
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}")


def _validate_palette_color(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or value != value.strip() or len(value) > 128:
        _fail(
            "SGC_SCHEMA_PALETTE_COLOR",
            "Palette colors must be short, trimmed CSS color strings.",
            "Use a literal CSS color or a --st-* theme variable.",
            subject,
        )
    lowered = value.casefold()
    if any(token in lowered for token in ("url(", "image(", "image-set(", "attr(")):
        _fail(
            "SGC_SCHEMA_PALETTE_REFERENCE",
            "Palette colors cannot contain external or document paint references.",
            "Use a literal CSS color or a --st-* theme variable.",
            subject,
        )
    if not any(
        pattern.fullmatch(value)
        for pattern in (_HEX_COLOR, _COLOR_KEYWORD, _COLOR_FUNCTION, _THEME_VARIABLE)
    ):
        _fail(
            "SGC_SCHEMA_PALETTE_COLOR",
            f"Unsupported CSS color syntax {value!r}.",
            "Use hex, a named color, a supported color function, or var(--st-*).",
            subject,
        )


def validate(
    schema: GraphSchema,
    graph: GraphData,
    *,
    max_elements: int = 700,
    max_data_bytes: int = 2_000_000,
    renderer_registry: RendererRegistry | None = None,
) -> None:
    """Validate a graph completely before it crosses the component boundary."""

    if max_elements <= 0:
        _fail(
            "SGC_BUDGET_INVALID",
            "max_elements must be positive.",
            "Pass a positive integer element budget.",
        )
    if max_data_bytes <= 0:
        _fail(
            "SGC_DATA_BUDGET_INVALID",
            "max_data_bytes must be positive.",
            "Pass a positive serialized-data budget.",
        )
    if len(graph.nodes) + len(graph.edges) > max_elements:
        _fail(
            "SGC_BUDGET_EXCEEDED",
            f"Graph has {len(graph.nodes)} nodes and {len(graph.edges)} edges, "
            f"exceeding the {max_elements}-element budget.",
            "Window the graph in the host application or increase max_elements.",
        )
    _validate_graph_data(graph, max_data_bytes=max_data_bytes)
    for name, tone in schema.palette.items():
        if not name or not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            _fail(
                "SGC_SCHEMA_PALETTE_NAME",
                f"Palette tone name {name!r} is invalid.",
                "Use a lowercase CSS-safe symbolic tone name.",
                name,
            )
        _validate_palette_color(tone.light, subject=f"palette:{name}.light")
        if tone.dark is not None:
            _validate_palette_color(tone.dark, subject=f"palette:{name}.dark")
    for key, node_declaration in schema.node_types.items():
        if not key or key != node_declaration.name:
            _fail(
                "SGC_SCHEMA_NODE_TYPE_NAME",
                "Node type mapping keys must be non-empty and match their names.",
                "Use the same stable name for the mapping key and declaration.",
                key,
            )
        palette_names = BUILTIN_PALETTE.keys() | schema.palette.keys()
        node_tones = {
            node_declaration.style.fill,
            node_declaration.style.stroke,
            node_declaration.style.text,
        }
        if unknown_tones := node_tones - palette_names:
            _fail(
                "SGC_SCHEMA_STYLE_TONE",
                "Node style references unknown palette tones: "
                f"{sorted(unknown_tones)}.",
                "Declare each symbolic tone in the schema palette.",
                key,
            )
        if (
            not all(
                math.isfinite(value)
                for value in (
                    node_declaration.style.width,
                    node_declaration.style.height,
                    node_declaration.style.radius,
                )
            )
            or node_declaration.style.width <= 0
            or node_declaration.style.height <= 0
            or node_declaration.style.radius < 0
        ):
            _fail(
                "SGC_SCHEMA_NODE_GEOMETRY",
                "Node type dimensions must be positive.",
                "Set positive width and height values.",
                key,
            )
        names = [port.name for port in node_declaration.ports]
        if duplicates := _duplicates(names):
            _fail(
                "SGC_SCHEMA_DUPLICATE_PORT",
                f"Node type has duplicate ports: {sorted(duplicates)}.",
                "Give every port on the node type a unique name.",
                key,
            )
        binding_names = [binding.name for binding in node_declaration.badges]
        if duplicates := _duplicates(binding_names):
            _fail(
                "SGC_SCHEMA_DUPLICATE_BINDING",
                f"Node type has duplicate badge bindings: {sorted(duplicates)}.",
                "Give every badge binding on the node type a unique name.",
                key,
            )
        for binding in node_declaration.badges:
            region = binding.region
            if (
                not all(
                    math.isfinite(value)
                    for value in (region.x, region.y, region.width, region.height)
                )
                or region.width <= 0
                or region.height <= 0
            ):
                _fail(
                    "SGC_SCHEMA_BADGE_REGION",
                    "Badge regions require finite coordinates and positive dimensions.",
                    "Correct the fixed region geometry.",
                    f"{key}.{binding.name}",
                )
            _json_value(binding.options, subject=f"{key}.{binding.name}.options")
            if renderer_registry is None:
                message = (
                    f"Badge binding {binding.name!r} requires an explicit "
                    "renderer registry."
                )
                _fail(
                    "SGC_RENDERER_NOT_ENABLED",
                    message,
                    "Call enable_renderers() and pass its result to graph_canvas().",
                    binding.kind,
                )
            renderer_registry.require(binding.kind, binding.transport.value)
    for key, edge_declaration in schema.edge_types.items():
        if not key or key != edge_declaration.name:
            _fail(
                "SGC_SCHEMA_EDGE_TYPE_NAME",
                "Edge type mapping keys must be non-empty and match their names.",
                "Use the same stable name for the mapping key and declaration.",
                key,
            )
        if (
            not math.isfinite(edge_declaration.style.width)
            or edge_declaration.style.width <= 0
        ):
            _fail(
                "SGC_SCHEMA_EDGE_GEOMETRY",
                "Edge widths must be finite and positive.",
                "Set a finite positive edge width.",
                key,
            )
        if edge_declaration.style.stroke not in (
            BUILTIN_PALETTE.keys() | schema.palette.keys()
        ):
            _fail(
                "SGC_SCHEMA_STYLE_TONE",
                "Edge style references unknown palette tone "
                f"{edge_declaration.style.stroke!r}.",
                "Declare the symbolic tone in the schema palette.",
                key,
            )
        _validate_endpoint_types(edge_declaration, schema)

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
        bindings = {
            binding.name: binding for binding in schema.node_types[node.type].badges
        }
        undeclared = node.badges.keys() - bindings.keys()
        if undeclared:
            _fail(
                "SGC_GRAPH_BADGE_BINDING",
                f"Node supplies undeclared badge bindings: {sorted(undeclared)}.",
                "Declare each binding on the node type or remove its data.",
                node.id,
            )
        missing_required = [
            name
            for name, binding in bindings.items()
            if binding.required and name not in node.badges
        ]
        if missing_required:
            _fail(
                "SGC_GRAPH_BADGE_REQUIRED",
                f"Node is missing required badge data: {missing_required}.",
                "Supply data for every required badge binding.",
                node.id,
            )
        if (
            node.width is not None
            and (not math.isfinite(node.width) or node.width <= 0)
        ) or (
            node.height is not None
            and (not math.isfinite(node.height) or node.height <= 0)
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
        edge_declaration = schema.edge_types[edge.type]
        source = nodes[edge.source]
        target = nodes[edge.target]
        if (
            not isinstance(edge_declaration.source_types, AnyNodeType)
            and source.type not in edge_declaration.source_types
        ):
            _fail(
                "SGC_GRAPH_EDGE_SOURCE_TYPE",
                f"Source node type {source.type!r} is not allowed.",
                "Use an allowed source type or update the edge declaration.",
                edge.id,
            )
        if (
            not isinstance(edge_declaration.target_types, AnyNodeType)
            and target.type not in edge_declaration.target_types
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
