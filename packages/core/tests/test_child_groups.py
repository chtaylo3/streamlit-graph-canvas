from __future__ import annotations

import pytest
from streamlit_graph_canvas import (
    ChildGroup,
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    GroupDirection,
    GroupDisplay,
    Node,
    NodeType,
    ValidationError,
    serialize_graph,
)


def schema(*groups: ChildGroup) -> GraphSchema:
    return GraphSchema(
        node_types={
            "manifest": NodeType("manifest", child_groups=groups),
            "package": NodeType("package"),
        },
        edge_types={
            "depends_on": EdgeType("depends_on"),
            "resolves": EdgeType("resolves"),
        },
    )


def graph(count: int = 4, edge_type: str = "resolves") -> GraphData:
    return GraphData(
        (
            Node("m", "manifest", "uv.lock"),
            *(Node(f"p{i}", "package", f"pkg-{i}") for i in range(count)),
        ),
        tuple(Edge(f"e{i}", "m", f"p{i}", edge_type) for i in range(count)),
    )


def test_child_groups_reach_the_envelope_sorted_by_edge_type() -> None:
    serialized = serialize_graph(
        schema(
            ChildGroup("resolves", label="Resolved packages", threshold=3),
            ChildGroup("depends_on", label="Direct dependencies"),
        ),
        graph(),
    )
    declared = serialized.envelope["schema"]["nodeTypes"]["manifest"]["childGroups"]
    assert [group["edgeType"] for group in declared] == ["depends_on", "resolves"]
    assert declared[1] == {
        "edgeType": "resolves",
        "label": "Resolved packages",
        "threshold": 3,
        "direction": "right",
        "collapsed": True,
        "display": "cutoff",
    }


def test_a_node_type_without_groups_serializes_an_empty_list() -> None:
    serialized = serialize_graph(schema(), graph())
    node_types = serialized.envelope["schema"]["nodeTypes"]
    assert node_types["manifest"]["childGroups"] == []
    assert node_types["package"]["childGroups"] == []


def test_child_groups_participate_in_the_topology_hash() -> None:
    """Grouping changes what is drawn, so it must invalidate the topology."""

    plain = serialize_graph(schema(), graph())
    grouped = serialize_graph(schema(ChildGroup("resolves")), graph())
    assert plain.topology_hash != grouped.topology_hash


def test_group_label_defaults_to_its_edge_type() -> None:
    assert ChildGroup("resolves").title == "resolves"
    assert ChildGroup("resolves", label="Resolved").title == "Resolved"


def test_a_group_must_reference_a_declared_edge_type() -> None:
    with pytest.raises(ValidationError, match="SGC_SCHEMA_CHILD_GROUP_EDGE_TYPE"):
        serialize_graph(schema(ChildGroup("not_declared")), graph())


def test_a_node_type_cannot_group_one_edge_type_twice() -> None:
    with pytest.raises(ValueError, match="more than once"):
        NodeType(
            "manifest",
            child_groups=(ChildGroup("resolves"), ChildGroup("resolves")),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"edge_type": ""},
        {"edge_type": "resolves", "threshold": 0},
        {"edge_type": "resolves", "threshold": True},
        {"edge_type": "resolves", "threshold": 1.5},
        {"edge_type": "resolves", "threshold": "8"},
        {"edge_type": "resolves", "display": "tree"},
        {"edge_type": "resolves", "collapsed": 1},
        {"edge_type": "resolves", "direction": "right"},
    ],
)
def test_child_group_rejects_invalid_declarations(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ChildGroup(**kwargs)  # type: ignore[arg-type]


def test_group_direction_round_trips_through_the_envelope() -> None:
    serialized = serialize_graph(
        schema(ChildGroup("resolves", direction=GroupDirection.DOWN, collapsed=False)),
        graph(),
    )
    declared = serialized.envelope["schema"]["nodeTypes"]["manifest"]["childGroups"][0]
    assert declared["direction"] == "down"
    assert declared["collapsed"] is False


@pytest.mark.parametrize("display", list(GroupDisplay))
def test_display_mode_changes_topology_but_not_graph_identity(
    display: GroupDisplay,
) -> None:
    result = serialize_graph(schema(ChildGroup("resolves", display=display)), graph())
    assert (
        result.envelope["schema"]["nodeTypes"]["manifest"]["childGroups"][0]["display"]
        == display.value
    )
    assert len(result.envelope["topology"]["nodes"]) == 5


def test_edge_emphasis_and_optional_are_presentation_only() -> None:
    from dataclasses import replace

    plain = graph()
    styled = replace(
        plain,
        edges=tuple(
            replace(edge, emphasized=True, optional=True) for edge in plain.edges
        ),
    )
    a = serialize_graph(schema(), plain)
    b = serialize_graph(schema(), styled)
    assert a.topology_hash == b.topology_hash
    assert a.presentation_hash != b.presentation_hash
    assert all(edge["type"] == "resolves" for edge in b.envelope["topology"]["edges"])
    assert all(
        edge["emphasized"] and edge["optional"]
        for edge in b.envelope["presentation"]["edges"]
    )
