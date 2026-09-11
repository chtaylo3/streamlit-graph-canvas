"""Pre-pack a schema's badge tiles so no session pays the first-render cost.

A badge binding's tile set is a function of its renderer, its options, the value
domain the application feeds it, the palette, the theme, and the device-scale
bucket. When an application can enumerate that domain — four severities, a
bounded count range, a fixed set of statuses — the tiles can be packed once at
startup instead of on whichever session happens to arrive first.

Because the atlas cache is process-global and content-addressed, warming it once
serves every session in the process. That improves on the old tenant-scoped
cache, which at best made the *second* session cheap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .atlas import AtlasPolicy, atlas_cache, resolution_bucket
from .images import SpriteCatalog
from .model import GraphData, GraphSchema, Node, Transport
from .renderers import RendererRegistry
from .serialization import serialize_graph
from .sprites import SpriteRef

DEFAULT_THEMES: tuple[str, ...] = ("light", "dark")
DEFAULT_RESOLUTIONS: tuple[float, ...] = (1.0, 1.5, 2.0)


@dataclass(frozen=True, slots=True)
class WarmingResult:
    """What a warming pass produced."""

    combinations: int
    pages: int
    bytes: int

    def __str__(self) -> str:
        return (
            f"warmed {self.combinations} theme/resolution combinations into "
            f"{self.pages} pages ({self.bytes} bytes)"
        )


def warm_atlas(
    schema: GraphSchema,
    badge_values: Mapping[str, Mapping[str, Sequence[object]]],
    *,
    renderer_registry: RendererRegistry | None = None,
    sprite_catalog: SpriteCatalog | None = None,
    atlas_policy: AtlasPolicy | None = None,
    themes: Iterable[str] = DEFAULT_THEMES,
    resolutions: Iterable[float] = DEFAULT_RESOLUTIONS,
    sprite_ids: Mapping[str, Sequence[str]] | None = None,
) -> WarmingResult:
    """Rasterize and pack every tile a schema can produce for the given values.

    ``badge_values`` maps a node type to each of its badge names to the values
    that badge may receive. Only bindings whose transport rasterizes are worth
    warming; PRIMS bindings are rendered per request and never enter the atlas.

    ``sprite_ids`` maps a node type to the catalog IDs its sprite bindings may
    reference, and is needed only when a static catalog is in use.

    Call this once during application startup, after the renderer registry is
    built. Warming is a cache-population side effect: the return value reports
    what was packed, and callers may ignore it.
    """

    policy = atlas_policy or AtlasPolicy()
    cache = atlas_cache(policy)
    sprite_ids = sprite_ids or {}
    combinations = 0

    for theme in themes:
        for resolution in resolutions:
            nodes = tuple(_sample_nodes(schema, badge_values, sprite_ids, resolution))
            if not nodes:
                continue
            serialize_graph(
                schema,
                GraphData(nodes, ()),
                max_elements=max(len(nodes) * 2, 700),
                renderer_registry=renderer_registry,
                sprite_catalog=sprite_catalog,
                atlas_cache=cache,
                atlas_policy=policy,
                atlas_theme=theme,
                atlas_resolution=resolution,
            )
            combinations += 1

    snapshot = cache.snapshot()
    return WarmingResult(
        combinations=combinations, pages=snapshot["pages"], bytes=snapshot["bytes"]
    )


def _sample_nodes(
    schema: GraphSchema,
    badge_values: Mapping[str, Mapping[str, Sequence[object]]],
    sprite_ids: Mapping[str, Sequence[str]],
    resolution: float,
) -> list[Node]:
    """Build one synthetic node per distinct value combination worth packing.

    Each node carries a single badge value so a node is emitted per value rather
    than per cross product, which keeps the synthetic graph linear in the size of
    the declared domains.
    """

    # Only a rasterizing transport contributes tiles; PRIMS renders per request.
    raster = {Transport.ATLAS, Transport.RASTER}
    nodes: list[Node] = []
    bucket = resolution_bucket(resolution)
    for type_name, declaration in schema.node_types.items():
        declared = badge_values.get(type_name, {})
        for binding in declaration.badges:
            if binding.transport not in raster:
                continue
            for index, value in enumerate(declared.get(binding.name, ())):
                nodes.append(
                    Node(
                        f"warm-{type_name}-{binding.name}-{bucket}-{index}",
                        type_name,
                        "warm",
                        badges={binding.name: value},
                    )
                )
        for sprite_binding in declaration.sprites:
            for index, catalog_id in enumerate(sprite_ids.get(type_name, ())):
                nodes.append(
                    Node(
                        f"warm-{type_name}-{sprite_binding.name}-{bucket}"
                        f"-sprite-{index}",
                        type_name,
                        "warm",
                        sprites={sprite_binding.name: SpriteRef(catalog_id)},
                    )
                )
    return nodes
