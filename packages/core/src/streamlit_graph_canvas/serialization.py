"""Versioned deterministic component envelopes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .model import AnyNodeType, GraphData, GraphSchema
from .validation import validate

CODEC_VERSION = 1


@dataclass(frozen=True, slots=True)
class SerializedGraph:
    envelope: dict[str, Any]
    topology_hash: str
    presentation_hash: str


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _allowed(value: frozenset[str] | AnyNodeType) -> list[str] | str:
    return "*" if isinstance(value, AnyNodeType) else sorted(value)


def serialize_graph(
    schema: GraphSchema, graph: GraphData, *, max_elements: int = 700
) -> SerializedGraph:
    """Validate and serialize stable topology separately from presentation."""

    validate(schema, graph, max_elements=max_elements)
    schema_data = {
        "nodeTypes": {
            name: {
                "name": kind.name,
                "style": asdict(kind.style),
                "ports": [asdict(port) for port in kind.ports],
            }
            for name, kind in sorted(schema.node_types.items())
        },
        "edgeTypes": {
            name: {
                "name": kind.name,
                "sourceTypes": _allowed(kind.source_types),
                "targetTypes": _allowed(kind.target_types),
                "style": asdict(kind.style),
            }
            for name, kind in sorted(schema.edge_types.items())
        },
        "palette": {
            name: asdict(tone) for name, tone in sorted(schema.palette.items())
        },
    }
    topology = {
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "width": node.width,
                "height": node.height,
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
                "sourcePort": edge.source_port,
                "targetPort": edge.target_port,
            }
            for edge in graph.edges
        ],
    }
    presentation = {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "data": dict(node.data),
                "disabled": node.disabled,
                "dimmed": node.dimmed,
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "label": edge.label,
                "data": dict(edge.data),
                "dimmed": edge.dimmed,
            }
            for edge in graph.edges
        ],
    }
    topology_hash = _hash({"schema": schema_data, "topology": topology})
    presentation_hash = _hash(presentation)
    return SerializedGraph(
        envelope={
            "codecVersion": CODEC_VERSION,
            "schema": schema_data,
            "topology": topology,
            "presentation": presentation,
            "topologyHash": topology_hash,
            "presentationHash": presentation_hash,
        },
        topology_hash=topology_hash,
        presentation_hash=presentation_hash,
    )
