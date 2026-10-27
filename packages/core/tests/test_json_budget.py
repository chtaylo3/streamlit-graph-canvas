from __future__ import annotations

import json
import math
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    ValidationError,
    validate,
)
from streamlit_graph_canvas.json_budget import JsonLimitError, bounded_json_size

LIMITS = {
    "max_bytes": 10_000_000,
    "max_depth": 32,
    "max_string_chars": 10_000,
    "max_collection_items": 10_000,
    "max_values": 1_000_000,
}
SAFE_INTEGER = 2**53 - 1

scalars = (
    st.none()
    | st.booleans()
    | st.integers(-SAFE_INTEGER, SAFE_INTEGER)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text()
)
json_trees = st.recursive(
    scalars,
    lambda children: (
        st.lists(children, max_size=6)
        | st.dictionaries(st.text(max_size=8), children, max_size=6)
    ),
    max_leaves=40,
)


def compact(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, separators=(",", ":")).encode())


@settings(max_examples=300, deadline=None)
@given(json_trees)
def test_size_equals_compact_json_encoding(value: Any) -> None:
    assert bounded_json_size(value, **LIMITS) == compact(value)


@settings(max_examples=200, deadline=None)
@given(json_trees, st.integers(min_value=1, max_value=400))
def test_byte_limit_is_exact(value: Any, limit: int) -> None:
    size = compact(value)
    if size <= limit:
        assert bounded_json_size(value, **{**LIMITS, "max_bytes": limit}) == size
    else:
        with pytest.raises(JsonLimitError) as error:
            bounded_json_size(value, **{**LIMITS, "max_bytes": limit})
        assert error.value.kind == "size"


def kind_of(value: Any, **limits: int) -> str:
    with pytest.raises(JsonLimitError) as error:
        bounded_json_size(value, **{**LIMITS, **limits})
    return error.value.kind


@pytest.mark.parametrize("value", [SAFE_INTEGER, -SAFE_INTEGER, True, False])
def test_safe_integer_boundary_is_inclusive(value: int) -> None:
    assert bounded_json_size(value, **LIMITS) == compact(value)


@pytest.mark.parametrize("value", [2**53, -(2**53), 10**400])
def test_integers_outside_the_javascript_safe_range_fail(value: int) -> None:
    assert kind_of(value) == "integer"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_fail(value: float) -> None:
    assert kind_of([1, {"x": value}]) == "number"


@pytest.mark.parametrize("value", [{1: "x"}, {None: "x"}, {("a",): "x"}])
def test_non_string_object_keys_fail(value: dict[Any, Any]) -> None:
    assert kind_of(value) == "key"


@pytest.mark.parametrize("value", [{1, 2}, b"bytes", object(), 1j, frozenset()])
def test_unsupported_types_fail(value: object) -> None:
    assert kind_of({"nested": [value]}) == "type"


def nested(depth: int) -> Any:
    value: Any = 0
    for _ in range(depth):
        value = [value]
    return value


def test_depth_limit_boundary() -> None:
    assert bounded_json_size(nested(4), **{**LIMITS, "max_depth": 4})
    assert kind_of(nested(5), max_depth=4) == "depth"


def test_string_limit_counts_characters_not_bytes() -> None:
    assert bounded_json_size("é" * 4, **{**LIMITS, "max_string_chars": 4})
    assert kind_of("é" * 5, max_string_chars=4) == "string"
    assert kind_of({"k" * 5: 1}, max_string_chars=4) == "string"


@pytest.mark.parametrize(
    "make", [lambda n: list(range(n)), lambda n: dict.fromkeys(map(str, range(n)), 0)]
)
def test_collection_limit_boundary(make: Any) -> None:
    assert bounded_json_size(make(3), **{**LIMITS, "max_collection_items": 3})
    assert kind_of(make(4), max_collection_items=3) == "collection"


def test_value_count_limit_includes_containers_and_keys() -> None:
    # One array + three scalars = four values.
    assert bounded_json_size([1, 2, 3], **{**LIMITS, "max_values": 4})
    assert kind_of([1, 2, 3], max_values=3) == "values"
    # Object keys count as values too: object + key + value = three.
    assert kind_of({"k": 1}, max_values=2) == "values"


def schema() -> GraphSchema:
    return GraphSchema({"item": NodeType("item")}, {"link": EdgeType("link")})


@pytest.mark.parametrize(
    ("data", "code"),
    [
        ({"n": 2**53}, "SGC_DATA_INTEGER"),
        ({"n": math.nan}, "SGC_DATA_NUMBER"),
        ({1: "x"}, "SGC_DATA_KEY"),
        ({"s": {1, 2}}, "SGC_DATA_TYPE"),
        ({"d": nested(30)}, "SGC_DATA_DEPTH"),
        ({"s": "x" * 65_537}, "SGC_DATA_STRING_LIMIT"),
        ({"c": list(range(10_001))}, "SGC_DATA_COLLECTION_LIMIT"),
    ],
)
def test_graph_data_limit_kinds_map_to_stable_codes(
    data: dict[Any, Any], code: str
) -> None:
    for graph in (
        GraphData((Node("a", "item", "A", data=data),), ()),
        GraphData((Node("a", "item", "A"),), (Edge("e", "a", "a", "link", data=data),)),
    ):
        with pytest.raises(ValidationError) as error:
            validate(schema(), graph)
        assert error.value.diagnostic.code == code


def test_graph_value_count_limit_has_a_stable_code() -> None:
    nodes = tuple(
        Node(f"n{i}", "item", "N", data={"v": list(range(9_000))}) for i in range(12)
    )
    with pytest.raises(ValidationError) as error:
        validate(schema(), GraphData(nodes, ()), max_data_bytes=10_000_000)
    assert error.value.diagnostic.code == "SGC_DATA_VALUES_LIMIT"
