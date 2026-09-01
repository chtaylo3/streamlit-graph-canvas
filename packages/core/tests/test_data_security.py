import json
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from streamlit_graph_canvas import (
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeStyle,
    NodeType,
    ValidationError,
    serialize_graph,
    validate,
)
from streamlit_graph_canvas.contract import (
    MAX_COLLECTION_ITEMS,
    MAX_DATA_STRING_CHARS,
)

SCHEMA = GraphSchema(
    node_types={"item": NodeType("item")},
    edge_types={"link": EdgeType("link")},
)


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, b"bytes", object(), {1: "bad"}, 2**53]
)
def test_non_json_graph_data_fails_before_serialization(value) -> None:
    graph = GraphData(nodes=(Node("a", "item", "A", data={"value": value}),), edges=())
    with pytest.raises(ValidationError):
        serialize_graph(SCHEMA, graph)


def test_deeply_nested_data_is_bounded() -> None:
    value: object = "leaf"
    for _ in range(22):
        value = [value]
    graph = GraphData(nodes=(Node("a", "item", "A", data={"value": value}),), edges=())
    with pytest.raises(ValidationError) as error:
        serialize_graph(SCHEMA, graph)
    assert error.value.diagnostic.code == "SGC_DATA_DEPTH"


def test_serialized_graph_data_size_is_bounded() -> None:
    graph = GraphData(
        nodes=(Node("a", "item", "A", data={"value": "x" * 100}),), edges=()
    )
    with pytest.raises(ValidationError) as error:
        validate(SCHEMA, graph, max_data_bytes=50)
    assert error.value.diagnostic.code == "SGC_DATA_SIZE"


def test_graph_budget_matches_compact_json_bytes_exactly() -> None:
    graph = GraphData(nodes=(Node("a", "item", "é", data={"value": "雪"}),), edges=())
    measured = {
        "nodes": [
            {
                "id": "a",
                "type": "item",
                "label": "é",
                "data": {"value": "雪"},
                "badges": {},
            }
        ],
        "edges": [],
    }
    exact = len(json.dumps(measured, allow_nan=False, separators=(",", ":")).encode())
    validate(SCHEMA, graph, max_data_bytes=exact)
    with pytest.raises(ValidationError) as error:
        validate(SCHEMA, graph, max_data_bytes=exact - 1)
    assert error.value.diagnostic.code == "SGC_DATA_SIZE"


def test_graph_strings_and_collection_breadth_fail_during_budget_walk() -> None:
    graph = GraphData(
        nodes=(
            Node(
                "a",
                "item",
                "A",
                data={"value": "x" * (MAX_DATA_STRING_CHARS + 1)},
            ),
        ),
        edges=(),
    )
    with pytest.raises(ValidationError) as error:
        validate(SCHEMA, graph)
    assert error.value.diagnostic.code == "SGC_DATA_STRING_LIMIT"

    broad = GraphData(
        nodes=(
            Node(
                "a",
                "item",
                "A",
                data={"value": [None] * (MAX_COLLECTION_ITEMS + 1)},
            ),
        ),
        edges=(),
    )
    with pytest.raises(ValidationError) as error:
        validate(SCHEMA, broad)
    assert error.value.diagnostic.code == "SGC_DATA_COLLECTION_LIMIT"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_schema_geometry_is_rejected(value: float) -> None:
    schema = GraphSchema(
        node_types={"item": NodeType("item", style=NodeStyle(width=value))},
        edge_types={},
    )
    with pytest.raises(ValidationError) as error:
        serialize_graph(schema, GraphData((), ()))
    assert error.value.diagnostic.code == "SGC_SCHEMA_NODE_GEOMETRY"


@given(st.text(max_size=200))
def test_arbitrary_labels_remain_plain_serialized_text(label: str) -> None:
    graph = GraphData(nodes=(Node("a", "item", label),), edges=())
    payload = serialize_graph(SCHEMA, graph).envelope
    assert payload["presentation"]["nodes"][0]["label"] == label
