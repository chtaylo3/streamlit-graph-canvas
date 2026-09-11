from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from streamlit_graph_canvas import (
    AtlasPolicy,
    BadgeBinding,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PaletteTone,
    Region,
    Transport,
    atlas_cache,
    atlas_cache_snapshot,
    enable_renderers,
    reset_atlas_caches,
    serialize_graph,
    warm_atlas,
)

_COUNT_CHIP = "streamlit-graph-canvas/contrib/count-chip"
_PALETTE = {
    "accent": PaletteTone("#2563eb", "#60a5fa"),
    "on_accent": PaletteTone("#ffffff", "#0f172a"),
}


@pytest.fixture(autouse=True)
def _clean_caches() -> Iterator[None]:
    reset_atlas_caches()
    yield
    reset_atlas_caches()


def schema(transport: Transport = Transport.RASTER) -> GraphSchema:
    return GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(
                    BadgeBinding(
                        "count",
                        _COUNT_CHIP,
                        Region.at(0, 0, 42, 22),
                        transport=transport,
                    ),
                ),
            )
        },
        edge_types={},
        palette=_PALETTE,
    )


def test_warming_packs_the_declared_value_domain() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    result = warm_atlas(
        schema(),
        {"item": {"count": [1, 2, 3]}},
        renderer_registry=registry,
        themes=("light",),
        resolutions=(1.0,),
    )
    assert result.combinations == 1
    assert result.pages >= 1
    assert atlas_cache_snapshot()["pages"] == result.pages


def test_warming_covers_every_theme_and_resolution() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    single = warm_atlas(
        schema(),
        {"item": {"count": [1]}},
        renderer_registry=registry,
        themes=("light",),
        resolutions=(1.0,),
    )
    reset_atlas_caches()
    every = warm_atlas(
        schema(),
        {"item": {"count": [1]}},
        renderer_registry=registry,
        themes=("light", "dark"),
        resolutions=(1.0, 1.5, 2.0),
    )
    assert every.combinations == 6
    # Theme and resolution are part of tile identity, so each combination adds
    # distinct bytes rather than reusing the light 1x tile.
    assert every.bytes > single.bytes


def test_a_warmed_cache_makes_the_first_render_a_cache_hit() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    policy = AtlasPolicy()
    graph = GraphData(
        tuple(
            Node(f"n{value}", "item", "N", badges={"count": value})
            for value in range(12)
        ),
        (),
    )

    warm_atlas(
        schema(),
        {"item": {"count": list(range(12))}},
        renderer_registry=registry,
        atlas_policy=policy,
        themes=("light",),
        resolutions=(1.0,),
    )
    pages_after_warming = atlas_cache_snapshot()["pages"]

    started = time.perf_counter()
    serialize_graph(
        schema(),
        graph,
        renderer_registry=registry,
        atlas_cache=atlas_cache(policy),
        atlas_policy=policy,
    )
    warmed_seconds = time.perf_counter() - started

    # A render against the warmed cache must add no pages: every tile it needs
    # was packed during warming.
    assert atlas_cache_snapshot()["pages"] == pages_after_warming

    reset_atlas_caches()
    started = time.perf_counter()
    serialize_graph(
        schema(),
        graph,
        renderer_registry=registry,
        atlas_cache=atlas_cache(policy),
        atlas_policy=policy,
    )
    cold_seconds = time.perf_counter() - started
    assert cold_seconds > warmed_seconds


def test_warming_ignores_bindings_that_never_rasterize() -> None:
    """PRIMS badges render per request, so warming them would pack nothing."""

    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    result = warm_atlas(
        schema(Transport.PRIMS),
        {"item": {"count": [1, 2, 3]}},
        renderer_registry=registry,
        themes=("light",),
        resolutions=(1.0,),
    )
    assert result.combinations == 0
    assert result.pages == 0


def test_warming_without_declared_values_is_a_no_op() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    result = warm_atlas(schema(), {}, renderer_registry=registry)
    assert result == type(result)(combinations=0, pages=0, bytes=0)
