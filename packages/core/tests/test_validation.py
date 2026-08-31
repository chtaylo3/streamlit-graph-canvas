import pytest
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PortSide,
    PortSpec,
    ValidationError,
    validate,
)


def schema() -> GraphSchema:
    return GraphSchema(
        node_types={
            "service": NodeType("service", ports=(PortSpec("out", PortSide.BOTTOM),)),
            "database": NodeType("database", ports=(PortSpec("in", PortSide.TOP),)),
        },
        edge_types={
            "calls": EdgeType("calls", frozenset({"service"}), frozenset({"database"}))
        },
    )


def test_directed_multigraph_and_self_loop_identities_are_explicit() -> None:
    graph = GraphData(
        nodes=(Node("api", "service", "API"), Node("db", "database", "DB")),
        edges=(
            Edge("primary", "api", "db", "calls", "out", "in"),
            Edge("retry", "api", "db", "calls", "out", "in"),
        ),
    )
    validate(schema(), graph)


def test_missing_endpoint_has_stable_diagnostic() -> None:
    graph = GraphData(
        nodes=(Node("api", "service", "API"),),
        edges=(Edge("bad", "api", "missing", "calls"),),
    )
    with pytest.raises(ValidationError) as error:
        validate(schema(), graph)
    assert error.value.diagnostic.code == "SGC_GRAPH_EDGE_ENDPOINT"


def test_combined_element_budget_is_strict() -> None:
    graph = GraphData(
        nodes=(Node("api", "service", "API"), Node("db", "database", "DB")),
        edges=(Edge("primary", "api", "db", "calls"),),
    )
    with pytest.raises(ValidationError) as error:
        validate(schema(), graph, max_elements=2)
    assert error.value.diagnostic.code == "SGC_BUDGET_EXCEEDED"
