"""Versioned deterministic component envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from functools import partial
from typing import Any

from .atlas import (
    AtlasCache,
    AtlasPolicy,
    atlas_content_key,
    rasterize_primitives,
    resolution_bucket,
    tenant_subject,
)
from .contract import CODEC_VERSION, RENDERER_API
from .errors import Diagnostic, ValidationError
from .model import BUILTIN_PALETTE, AnyNodeType, GraphData, GraphSchema, Transport
from .primitives import BadgeContext, validate_primitives
from .renderers import RendererRegistry
from .validation import validate


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
    atlas_cache: AtlasCache | None = None,
    atlas_policy: AtlasPolicy | None = None,
    atlas_tenant: str = "session",
    atlas_theme: str = "light",
    atlas_resolution: float = 1.0,
    atlas_known_pages: frozenset[str] = frozenset(),
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
            **BUILTIN_PALETTE,
            **{name: asdict(tone) for name, tone in sorted(schema.palette.items())},
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

    if atlas_theme not in {"light", "dark"}:
        raise ValueError("atlas_theme must be 'light' or 'dark'")
    if not atlas_tenant or len(atlas_tenant) > 128:
        raise ValueError("atlas_tenant must be a non-empty string of at most 128 chars")
    policy = atlas_policy or AtlasPolicy()
    cache = atlas_cache or AtlasCache(policy)
    bucket = resolution_bucket(atlas_resolution)
    atlas_pages: dict[str, dict[str, Any]] = {}
    removed_atlas_pages: set[str] = set()
    referenced_atlas_pages: set[str] = set()
    javascript_renderers: dict[str, dict[str, Any]] = {}
    resolved_palette = {
        name: (
            tone["dark"] if atlas_theme == "dark" and tone["dark"] else tone["light"]
        )
        for name, tone in {
            **BUILTIN_PALETTE,
            **{name: asdict(tone) for name, tone in schema.palette.items()},
        }.items()
    }

    def rendered_primitives(
        node: Any, binding: Any, renderer: Any, context: BadgeContext
    ) -> tuple[dict[str, Any], ...]:
        if renderer.implementation is None:
            raise ValidationError(
                Diagnostic(
                    "SGC_RENDERER_IMPLEMENTATION",
                    "Enabled raster/vector renderer has no Python implementation.",
                    "Correct the installed renderer manifest.",
                    binding.kind,
                )
            )
        try:
            primitives = renderer.implementation.render(
                node.badges[binding.name], binding.options, context
            )
            return validate_primitives(
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
                context = BadgeContext(
                    binding.region.width,
                    binding.region.height,
                    frozenset(BUILTIN_PALETTE.keys() | schema.palette.keys()),
                )
                badge["primitives"] = rendered_primitives(
                    node, binding, renderer, context
                )
            elif binding.transport is Transport.JAVASCRIPT:
                declaration = renderer.declaration
                if (
                    declaration.javascript_component is None
                    or declaration.javascript_entry is None
                    or renderer.javascript_hash is None
                ):
                    raise ValidationError(
                        Diagnostic(
                            "SGC_JAVASCRIPT_REGISTRATION",
                            "JavaScript renderer registration metadata is incomplete.",
                            "Rebuild the renderer wheel with component and entry "
                            "metadata.",
                            binding.kind,
                        )
                    )
                javascript_renderers[binding.kind] = {
                    "kind": binding.kind,
                    "component": declaration.javascript_component,
                    "entry": declaration.javascript_entry,
                    "version": renderer.version,
                    "rendererApi": RENDERER_API,
                    "assetHash": renderer.javascript_hash,
                    "buildIdentity": declaration.javascript_identity,
                }
                badge["data"] = node.badges[binding.name]
                badge["options"] = dict(binding.options)
            else:
                context = BadgeContext(
                    binding.region.width,
                    binding.region.height,
                    frozenset(BUILTIN_PALETTE.keys() | schema.palette.keys()),
                )
                primitives = rendered_primitives(node, binding, renderer, context)
                content_key = atlas_content_key(
                    {
                        "kind": binding.kind,
                        "rendererVersion": renderer.version,
                        "options": dict(binding.options),
                        "data": node.badges[binding.name],
                        "palette": resolved_palette,
                        "theme": atlas_theme,
                        "width": binding.region.width,
                        "height": binding.region.height,
                        "resolution": bucket,
                        "primitives": primitives,
                    },
                    subject=f"{node.id}.{binding.name}",
                )
                lookup = cache.get_or_create(
                    tenant=atlas_tenant,
                    content_key=content_key,
                    create=partial(
                        rasterize_primitives,
                        primitives,
                        width=binding.region.width,
                        height=binding.region.height,
                        palette=resolved_palette,
                        bucket=bucket,
                        policy=policy,
                        subject=f"{node.id}.{binding.name}",
                    ),
                )
                removed_atlas_pages.update(lookup.evicted_page_ids)
                page = lookup.page
                referenced_atlas_pages.add(page.page_id)
                if page.page_id not in atlas_known_pages:
                    atlas_pages[page.page_id] = {
                        "pageId": page.page_id,
                        "contentSha256": hashlib.sha256(page.content).hexdigest(),
                        "mediaType": page.media_type,
                        "base64": base64.b64encode(page.content).decode("ascii"),
                        "width": page.width,
                        "height": page.height,
                    }
                badge["atlas"] = {
                    "pageId": page.page_id,
                    "x": 0,
                    "y": 0,
                    "width": page.width,
                    "height": page.height,
                    "resolution": bucket,
                }
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
    if evicted_active := referenced_atlas_pages & removed_atlas_pages:
        raise ValidationError(
            Diagnostic(
                "SGC_ATLAS_WORKING_SET_LIMIT",
                f"ATLAS cache limits evicted {len(evicted_active)} pages still "
                "required by the current graph.",
                "Increase the reviewed tenant limits or reduce ATLAS cardinality.",
                tenant_subject(atlas_tenant),
            )
        )
    topology_hash = _hash({"schema": schema_data, "topology": topology})
    presentation_hash = _hash(presentation)
    return SerializedGraph(
        envelope={
            "codecVersion": CODEC_VERSION,
            "schema": schema_data,
            "topology": topology,
            "presentation": presentation,
            "javascriptRenderers": list(javascript_renderers.values()),
            "atlas": {
                "pages": list(atlas_pages.values()),
                "removedPageIds": sorted(removed_atlas_pages),
                "policy": {
                    "maxPages": policy.max_pages,
                    "maxBytes": policy.max_bytes,
                    "scope": policy.scope.value,
                },
                "theme": atlas_theme,
                "resolution": bucket,
            },
            "topologyHash": topology_hash,
            "presentationHash": presentation_hash,
        },
        topology_hash=topology_hash,
        presentation_hash=presentation_hash,
    )
