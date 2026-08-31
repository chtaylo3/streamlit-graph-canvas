"""Versioned deterministic component envelopes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .errors import Diagnostic, ValidationError
from .model import AnyNodeType, GraphData, GraphSchema, Transport
from .primitives import BadgeContext, validate_primitives
from .renderers import RendererRegistry
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
    schema: GraphSchema,
    graph: GraphData,
    *,
    max_elements: int = 700,
    renderer_registry: RendererRegistry | None = None,
) -> SerializedGraph:
    """Validate and serialize stable topology separately from presentation."""

    validate(
        schema,
        graph,
        max_elements=max_elements,
        renderer_registry=renderer_registry,
    )
    schema_data = {
        "nodeTypes": {
            name: {
                "name": kind.name,
                "style": asdict(kind.style),
                "ports": [asdict(port) for port in kind.ports],
                "badges": [
                    {
                        "name": binding.name,
                        "kind": binding.kind,
                        "region": asdict(binding.region),
                        "transport": binding.transport.value,
                        "layer": binding.layer,
                        "z": binding.z,
                    }
                    for binding in sorted(
                        kind.badges, key=lambda item: (item.layer, item.z)
                    )
                ],
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

    def badges_for(node: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for binding in sorted(
            schema.node_types[node.type].badges,
            key=lambda item: (item.layer, item.z),
        ):
            if binding.name not in node.badges:
                continue
            assert renderer_registry is not None  # Guaranteed by validation above.
            renderer = renderer_registry.require(binding.kind, binding.transport.value)
            badge: dict[str, Any] = {
                "name": binding.name,
                "kind": binding.kind,
                "transport": binding.transport.value,
                "region": asdict(binding.region),
                "layer": binding.layer,
                "z": binding.z,
            }
            if binding.transport is Transport.PRIMS:
                if renderer.implementation is None:
                    raise ValidationError(
                        Diagnostic(
                            "SGC_RENDERER_IMPLEMENTATION",
                            "Enabled PRIMS renderer has no Python implementation.",
                            "Correct the installed renderer manifest.",
                            binding.kind,
                        )
                    )
                context = BadgeContext(
                    binding.region.width,
                    binding.region.height,
                    frozenset(schema.palette),
                )
                try:
                    primitives = renderer.implementation.render(
                        node.badges[binding.name], binding.options, context
                    )
                    badge["primitives"] = validate_primitives(
                        primitives,
                        context,
                        subject=f"{node.id}.{binding.name}",
                    )
                except ValidationError:
                    raise
                except Exception as error:
                    raise ValidationError(
                        Diagnostic(
                            "SGC_RENDERER_EXECUTION",
                            f"Renderer failed with {type(error).__name__}: {error}.",
                            "Disable or correct the explicitly enabled renderer.",
                            binding.kind,
                        )
                    ) from error
            elif binding.transport is Transport.JAVASCRIPT:
                raise ValidationError(
                    Diagnostic(
                        "SGC_JAVASCRIPT_NOT_IMPLEMENTED",
                        "JavaScript transport is not available in this release.",
                        "Use PRIMS until the trusted bootstrap milestone is complete.",
                        binding.kind,
                    )
                )
            else:
                raise ValidationError(
                    Diagnostic(
                        "SGC_ATLAS_NOT_IMPLEMENTED",
                        "ATLAS transport is not available in this release.",
                        "Use PRIMS until the ATLAS milestone is complete.",
                        binding.kind,
                    )
                )
            result.append(badge)
        return result

    presentation = {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "data": dict(node.data),
                "badges": badges_for(node),
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
