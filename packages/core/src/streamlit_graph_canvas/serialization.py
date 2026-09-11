"""Versioned deterministic component envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .atlas import (
    AtlasCache,
    AtlasPolicy,
    atlas_content_key,
    rasterize_primitives_tile,
    resolution_bucket,
)
from .contract import CODEC_VERSION, RENDERER_API
from .errors import Diagnostic, ValidationError
from .images import SpriteCatalog, normalize_catalog
from .model import BUILTIN_PALETTE, AnyNodeType, GraphData, GraphSchema, Transport
from .primitives import BadgeContext, validate_primitives
from .renderers import RendererRegistry
from .sprites import RasterTile, prepare_static_tile, static_tile_content_key
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
    sprite_catalog: SpriteCatalog | None = None,
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
        sprite_catalog=sprite_catalog,
    )
    if atlas_theme not in {"light", "dark"}:
        raise ValueError("atlas_theme must be 'light' or 'dark'")
    if not atlas_tenant or len(atlas_tenant) > 128:
        raise ValueError("atlas_tenant must be a non-empty string of at most 128 chars")
    policy = atlas_policy or AtlasPolicy()
    cache = atlas_cache or AtlasCache(policy)
    bucket = resolution_bucket(atlas_resolution)
    normalized_catalog = (
        normalize_catalog(sprite_catalog, policy=policy)
        if sprite_catalog is not None
        else {}
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
                        kind.badges, key=lambda item: (item.layer, item.z, item.name)
                    )
                ],
                "sprites": [
                    {
                        "name": binding.name,
                        "region": asdict(binding.region),
                        "layer": binding.layer,
                        "z": binding.z,
                        "fit": binding.fit,
                    }
                    for binding in sorted(
                        kind.sprites, key=lambda item: (item.layer, item.z, item.name)
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
    resolved_palette = {
        name: (
            tone["dark"] if atlas_theme == "dark" and tone["dark"] else tone["light"]
        )
        for name, tone in {
            **BUILTIN_PALETTE,
            **{name: asdict(tone) for name, tone in schema.palette.items()},
        }.items()
    }
    javascript_renderers: dict[str, dict[str, Any]] = {}
    required_tiles: dict[str, RasterTile] = {}
    layers_by_node: dict[str, list[dict[str, Any]]] = {}

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
                primitives, context, subject=f"{node.id}.{binding.name}"
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

    for node in graph.nodes:
        layers: list[dict[str, Any]] = []
        declaration = schema.node_types[node.type]
        for binding in declaration.badges:
            if binding.name not in node.badges:
                continue
            assert renderer_registry is not None
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
                metadata = renderer.declaration
                if (
                    metadata.javascript_component is None
                    or metadata.javascript_entry is None
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
                    "component": metadata.javascript_component,
                    "entry": metadata.javascript_entry,
                    "version": renderer.version,
                    "rendererApi": RENDERER_API,
                    "assetHash": renderer.javascript_hash,
                    "buildIdentity": metadata.javascript_identity,
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
                if content_key not in required_tiles:
                    required_tiles[content_key] = rasterize_primitives_tile(
                        primitives,
                        content_key=content_key,
                        width=binding.region.width,
                        height=binding.region.height,
                        palette=resolved_palette,
                        bucket=bucket,
                        policy=policy,
                        subject=f"{node.id}.{binding.name}",
                    )
                badge["_tileKey"] = content_key
                badge["_locationField"] = (
                    "atlas" if binding.transport is Transport.ATLAS else "sprite"
                )
            layers.append(badge)
        for sprite_binding in declaration.sprites:
            if sprite_binding.name not in node.sprites:
                continue
            reference = node.sprites[sprite_binding.name]
            variants = normalized_catalog[reference.catalog_id]
            selected = variants.get("dark") if atlas_theme == "dark" else None
            selected = selected or variants["light"]
            tile_key = static_tile_content_key(
                selected,
                logical_width=sprite_binding.region.width,
                logical_height=sprite_binding.region.height,
                resolution=bucket,
                fit=sprite_binding.fit,
                subject=f"{node.id}.{sprite_binding.name}",
            )
            if tile_key not in required_tiles:
                required_tiles[tile_key] = prepare_static_tile(
                    selected,
                    logical_width=sprite_binding.region.width,
                    logical_height=sprite_binding.region.height,
                    resolution=bucket,
                    fit=sprite_binding.fit,
                    policy=policy,
                    subject=f"{node.id}.{sprite_binding.name}",
                )
            layers.append(
                {
                    "name": sprite_binding.name,
                    "kind": "static-sprite",
                    "transport": "sprite",
                    "region": asdict(sprite_binding.region),
                    "layer": sprite_binding.layer,
                    "z": sprite_binding.z,
                    "fit": sprite_binding.fit,
                    "accessibleText": reference.accessible_text,
                    "_tileKey": tile_key,
                    "_locationField": "sprite",
                }
            )
        layers_by_node[node.id] = sorted(
            layers, key=lambda item: (item["layer"], item["z"], item["name"])
        )

    packed = cache.resolve_tiles(tenant=atlas_tenant, tiles=required_tiles)
    atlas_pages = [
        {
            "pageId": page.page_id,
            "contentSha256": hashlib.sha256(page.content).hexdigest(),
            "mediaType": page.media_type,
            "base64": base64.b64encode(page.content).decode("ascii"),
            "width": page.width,
            "height": page.height,
        }
        for page in packed.referenced_pages
        if page.page_id not in atlas_known_pages
    ]
    for layers in layers_by_node.values():
        for layer in layers:
            content_key = layer.pop("_tileKey", None)
            location_field = layer.pop("_locationField", None)
            if content_key is None:
                continue
            location = packed.locations[content_key]
            layer[location_field] = {
                "pageId": location.page_id,
                "x": location.x,
                "y": location.y,
                "width": location.width,
                "height": location.height,
                "resolution": bucket,
            }

    presentation = {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "data": dict(node.data),
                "badges": layers_by_node[node.id],
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
    presentation_hash = _hash(
        {"presentation": presentation, "theme": atlas_theme, "resolution": bucket}
    )
    return SerializedGraph(
        envelope={
            "codecVersion": CODEC_VERSION,
            "schema": schema_data,
            "topology": topology,
            "presentation": presentation,
            "javascriptRenderers": list(javascript_renderers.values()),
            "atlas": {
                "pages": atlas_pages,
                "removedPageIds": sorted(packed.evicted_page_ids),
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
