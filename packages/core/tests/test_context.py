from dataclasses import replace

import pytest
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    ValidationError,
    add_sibling_context,
    serialize_graph,
)


def fixture():
    nodes = (
        Node("a", "account", "Account"),
        Node("r", "repo", "Focus"),
        Node("m", "manifest", "Manifest"),
        Node("s", "repo", "Sibling"),
        Node("t", "repo", "Third"),
        Node("x", "manifest", "Other manifest"),
    )
    edges = (
        Edge("ar", "a", "r", "owns"),
        Edge("rm", "r", "m", "contains"),
        Edge("as", "a", "s", "owns"),
        Edge("at", "a", "t", "owns"),
        Edge("sx", "s", "x", "contains"),
    )
    return GraphData(nodes[:3], edges[:2]), GraphData(nodes, edges)


def test_context_respects_budget_preserves_focus_and_excludes_descendants():
    visible, available = fixture()
    result = add_sibling_context(
        visible, available, "r", enabled=True, max_elements=7, opacity=0.8
    )
    assert [n.id for n in result.nodes] == ["a", "r", "m", "s"]
    assert (
        tuple(replace(n, layout_order=None) for n in result.nodes[:3]) == visible.nodes
    )
    assert result.edges[:2] == visible.edges
    assert result.nodes[-1].opacity == 0.8
    assert result.edges[-1].opacity == 0.8
    assert add_sibling_context(visible, available, "r") is visible
    assert (
        add_sibling_context(visible, available, "r", enabled=True, max_elements=5).edges
        == visible.edges
    )
    assert (
        add_sibling_context(
            visible,
            available,
            "r",
            enabled=True,
            relationship_types=frozenset({"other"}),
        )
        == visible
    )
    # Parallel parent links both consume budget; no partially connected sibling.
    available = replace(
        available, edges=(*available.edges, Edge("as2", "a", "s", "owns"))
    )
    result = add_sibling_context(visible, available, "r", enabled=True, max_elements=7)
    assert result.nodes[-1].id == "t"
    assert len(result.nodes) + len(result.edges) == 7


@pytest.mark.parametrize("opacity", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_opacity_rejected(opacity):
    visible, available = fixture()
    with pytest.raises(ValueError):
        add_sibling_context(visible, available, "r", enabled=True, opacity=opacity)
    schema = GraphSchema({"repo": NodeType("repo")}, {"owns": EdgeType("owns")})
    for graph in (
        GraphData((Node("r", "repo", "R", opacity=opacity),), ()),
        GraphData(
            (Node("r", "repo", "R"),), (Edge("e", "r", "r", "owns", opacity=opacity),)
        ),
    ):
        with pytest.raises(ValidationError, match="opacity"):
            serialize_graph(schema, graph)


def test_opacity_changes_presentation_without_changing_topology():
    schema = GraphSchema({"repo": NodeType("repo")}, {"owns": EdgeType("owns")})
    before = GraphData((Node("r", "repo", "R"),), (Edge("e", "r", "r", "owns"),))
    after = GraphData(
        (replace(before.nodes[0], opacity=0.2),),
        (replace(before.edges[0], opacity=0.8),),
    )
    a, b = serialize_graph(schema, before), serialize_graph(schema, after)
    assert a.topology_hash == b.topology_hash
    assert a.presentation_hash != b.presentation_hash
    assert b.envelope["presentation"]["nodes"][0]["opacity"] == 0.2
    assert b.envelope["presentation"]["edges"][0]["opacity"] == 0.8


def test_peer_order_survives_focus_switch():
    visible, available = fixture()
    first = add_sibling_context(visible, available, "r", enabled=True)
    other = GraphData((available.nodes[0], available.nodes[3]), (available.edges[2],))
    second = add_sibling_context(other, available, "s", enabled=True)

    def ranks(g):
        return {n.id: n.layout_order for n in g.nodes if n.type == "repo"}

    assert ranks(first) == ranks(second)
