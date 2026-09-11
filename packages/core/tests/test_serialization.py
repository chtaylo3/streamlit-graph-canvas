from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    serialize_graph,
)
from streamlit_graph_canvas.contract import CODEC_VERSION


def test_presentation_change_does_not_change_topology_hash() -> None:
    schema = GraphSchema(
        node_types={"item": NodeType("item")},
        edge_types={"link": EdgeType("link")},
    )
    before = GraphData(
        nodes=(Node("a", "item", "Before"), Node("b", "item", "B")),
        edges=(Edge("a-b", "a", "b", "link"),),
    )
    after = GraphData(
        nodes=(Node("a", "item", "After", dimmed=True), Node("b", "item", "B")),
        edges=(Edge("a-b", "a", "b", "link", label="changed"),),
    )
    left = serialize_graph(schema, before)
    right = serialize_graph(schema, after)
    assert left.topology_hash == right.topology_hash
    assert left.presentation_hash != right.presentation_hash
    assert left.envelope["codecVersion"] == CODEC_VERSION


def test_arrow_placement_serializes_and_rejects_invalid_values() -> None:
    import pytest
    from streamlit_graph_canvas import EdgeStyle, ValidationError

    for arrow in ("none", "source", "target", "both"):
        schema = GraphSchema(
            node_types={"item": NodeType("item")},
            edge_types={"link": EdgeType("link", style=EdgeStyle(arrow=arrow))},
        )
        result = serialize_graph(schema, GraphData(nodes=(), edges=()))
        assert result.envelope["schema"]["edgeTypes"]["link"]["style"]["arrow"] == arrow
    schema = GraphSchema(
        node_types={"item": NodeType("item")},
        edge_types={"link": EdgeType("link", style=EdgeStyle(arrow="invalid"))},
    )
    with pytest.raises(ValidationError, match="arrow"):
        serialize_graph(schema, GraphData(nodes=(), edges=()))


def test_layout_identity_separates_geometry_from_schema_appearance():
    from dataclasses import replace

    from streamlit_graph_canvas import ChildGroup, LabelPolicy, NodeStyle, PaletteTone

    graph = GraphData((Node("a", "item", "label"),), ())
    schema = GraphSchema(
        {"item": NodeType("item", child_groups=(ChildGroup("link", "Children"),))},
        {"link": EdgeType("link")},
    )
    before = serialize_graph(schema, graph)
    for changed in (
        replace(schema, label_policy=LabelPolicy(reveal_delay_ms=900)),
        replace(schema, palette={"custom": PaletteTone("red", "blue")}),
        replace(
            schema,
            node_types={
                "item": replace(schema.node_types["item"], style=NodeStyle(fill="text"))
            },
        ),
        replace(
            schema,
            node_types={
                "item": replace(
                    schema.node_types["item"],
                    child_groups=(ChildGroup("link", "Renamed"),),
                )
            },
        ),
    ):
        after = serialize_graph(changed, graph)
        assert after.envelope["layoutHash"] == before.envelope["layoutHash"]
        assert after.presentation_hash != before.presentation_hash
        # Preserve established action/topology invalidation semantics.
        assert after.topology_hash != before.topology_hash
    for kind in (
        replace(schema.node_types["item"], style=NodeStyle(width=240)),
        replace(
            schema.node_types["item"], child_groups=(ChildGroup("link", threshold=30),)
        ),
    ):
        after = serialize_graph(replace(schema, node_types={"item": kind}), graph)
        assert after.envelope["layoutHash"] != before.envelope["layoutHash"]
