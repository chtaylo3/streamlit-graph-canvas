from pathlib import Path

import pytest
from streamlit_graph_canvas import (
    BadgeBinding,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PaletteTone,
    Region,
    ValidationError,
    enable_renderers,
    serialize_graph,
)
from streamlit_graph_canvas_contrib import renderer_manifest


def test_static_renderer_manifest_is_packaged() -> None:
    path = renderer_manifest()
    assert isinstance(path, Path)
    assert path.name == "renderer.toml"
    assert path.is_file()


def test_stock_renderer_composes_through_public_core_api() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    schema = GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(
                    BadgeBinding(
                        "count",
                        "streamlit-graph-canvas/contrib/count-chip",
                        Region.at(145, -8, 42, 22),
                        required=True,
                    ),
                ),
            )
        },
        edge_types={"link": EdgeType("link")},
        palette={
            "accent": PaletteTone("#2563eb", "#60a5fa"),
            "on_accent": PaletteTone("#ffffff", "#0f172a"),
        },
    )
    graph = GraphData(nodes=(Node("a", "item", "A", badges={"count": 7}),), edges=())
    payload = serialize_graph(schema, graph, renderer_registry=registry).envelope
    badge = payload["presentation"]["nodes"][0]["badges"][0]
    assert [item["kind"] for item in badge["primitives"]] == ["rect", "text"]


def test_stock_renderer_failure_is_a_stable_core_diagnostic() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    schema = GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(
                    BadgeBinding(
                        "count",
                        "streamlit-graph-canvas/contrib/count-chip",
                        Region.at(0, 0, 42, 22),
                        required=True,
                    ),
                ),
            )
        },
        edge_types={},
        palette={
            "accent": PaletteTone("#2563eb"),
            "on_accent": PaletteTone("#ffffff"),
        },
    )
    graph = GraphData(
        nodes=(Node("a", "item", "A", badges={"count": "not-an-int"}),),
        edges=(),
    )
    with pytest.raises(ValidationError) as error:
        serialize_graph(schema, graph, renderer_registry=registry)
    assert error.value.diagnostic.code == "SGC_RENDERER_EXECUTION"
