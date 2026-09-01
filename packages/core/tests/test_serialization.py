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
