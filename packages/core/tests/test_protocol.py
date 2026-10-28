import math
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from streamlit_graph_canvas import Edge, GraphData, Node, ValidationError
from streamlit_graph_canvas.contract import MAX_ACTION_BATCH, MAX_SELECTION
from streamlit_graph_canvas.protocol import (
    CanvasViewport,
    parse_actions,
    parse_selection,
    parse_viewport,
)


def graph() -> GraphData:
    return GraphData(
        (Node("a", "service", "A"), Node("b", "worker", "B")),
        (Edge("a-b", "a", "b", "calls"),),
    )


def action(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "protocolVersion": 1,
        "seq": 1,
        "operationId": str(uuid.uuid4()),
        "gesture": "click",
        "nodeId": "a",
        "nodeType": "service",
        "topologyRevision": 2,
        "target": {"kind": "node"},
        "modifiers": {"shift": False, "meta": False, "alt": False},
    }
    value.update(updates)
    return value


def test_selection_reconciles_removed_nodes_and_duplicates() -> None:
    assert parse_selection(["a", "missing", "a"], graph()) == ("a",)


def test_selection_cardinality_and_identifier_lengths_are_bounded() -> None:
    with pytest.raises(ValidationError) as error:
        parse_selection(["a"] * (MAX_SELECTION + 1), graph())
    assert error.value.diagnostic.code == "SGC_STATE_SELECTION_LIMIT"
    with pytest.raises(ValidationError) as error:
        parse_selection(["x" * 513], graph())
    assert error.value.diagnostic.code == "SGC_STATE_SELECTION"


def test_viewport_requires_finite_bounded_values() -> None:
    assert parse_viewport({"x": 1, "y": -2, "zoom": 1.5}) == CanvasViewport(
        1.0, -2.0, 1.5
    )
    with pytest.raises(ValidationError) as error:
        parse_viewport({"x": math.nan, "y": 0, "zoom": 1})
    assert error.value.diagnostic.code == "SGC_STATE_VIEWPORT"


def test_actions_are_validated_deduplicated_and_topology_authoritative() -> None:
    accepted, acknowledged = parse_actions(
        [action()], graph(), topology_revision=2, acknowledged_sequence=0
    )
    assert [item.node_id for item in accepted] == ["a"]
    assert acknowledged == 1
    duplicate, acknowledged = parse_actions(
        [action()], graph(), topology_revision=2, acknowledged_sequence=1
    )
    assert duplicate == ()
    assert acknowledged == 1
    stale, acknowledged = parse_actions(
        [action(seq=2, topologyRevision=1)],
        graph(),
        topology_revision=2,
        acknowledged_sequence=1,
    )
    assert stale == ()
    assert acknowledged == 2


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"protocolVersion": 99}, "SGC_ACTION_PROTOCOL"),
        ({"protocolVersion": True}, "SGC_ACTION_PROTOCOL"),
        ({"protocolVersion": 1.0}, "SGC_ACTION_PROTOCOL"),
        ({"protocolVersion": "1"}, "SGC_ACTION_PROTOCOL"),
        ({"seq": 0}, "SGC_ACTION_SEQUENCE"),
        ({"operationId": "nope"}, "SGC_ACTION_OPERATION_ID"),
        ({"gesture": "double-click"}, "SGC_ACTION_GESTURE"),
        (
            {"modifiers": {"shift": 1, "meta": False, "alt": False}},
            "SGC_ACTION_MODIFIERS",
        ),
    ],
)
def test_malformed_actions_fail_closed(updates: dict[str, object], code: str) -> None:
    with pytest.raises(ValidationError) as error:
        parse_actions(
            [action(**updates)], graph(), topology_revision=2, acknowledged_sequence=0
        )
    assert error.value.diagnostic.code == code


def test_action_batch_and_identifier_lengths_are_bounded_before_parsing() -> None:
    with pytest.raises(ValidationError) as error:
        parse_actions(
            [action()] * (MAX_ACTION_BATCH + 1),
            graph(),
            topology_revision=2,
            acknowledged_sequence=0,
        )
    assert error.value.diagnostic.code == "SGC_ACTION_BATCH_LIMIT"
    with pytest.raises(ValidationError) as error:
        parse_actions(
            [action(nodeId="x" * 513)],
            graph(),
            topology_revision=2,
            acknowledged_sequence=0,
        )
    assert error.value.diagnostic.code == "SGC_ACTION_BYTES_LIMIT"


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=40),
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text(max_size=12), children, max_size=5)
    ),
    max_leaves=25,
)
ACTION_FIELDS = sorted(action())


@st.composite
def mutated_actions(draw: st.DrawFn) -> dict[str, object]:
    """A valid envelope with a few fields replaced, dropped, or added."""
    value = action()
    for name in draw(st.lists(st.sampled_from(ACTION_FIELDS), max_size=3)):
        if draw(st.booleans()):
            value[name] = draw(json_values)
        else:
            value.pop(name, None)
    if draw(st.booleans()):
        value[draw(st.text(min_size=1, max_size=8))] = draw(json_values)
    return value


@st.composite
def mutated_batches(draw: st.DrawFn) -> list[dict[str, object]]:
    """Batches with increasing sequences so the accept path is reachable."""
    items = draw(st.lists(mutated_actions(), max_size=4))
    for index, item in enumerate(items, start=1):
        if "seq" in item and item["seq"] == 1:
            item["seq"] = index
    return items


@settings(max_examples=300, deadline=None)
@given(st.one_of(json_values, mutated_batches()))
def test_untrusted_action_batches_only_parse_or_raise_diagnostics(
    value: object,
) -> None:
    node_types = {node.id: node.type for node in graph().nodes}
    try:
        accepted, acknowledged = parse_actions(
            value, graph(), topology_revision=2, acknowledged_sequence=0
        )
    except ValidationError as error:
        assert error.diagnostic.code.startswith("SGC_ACTION_")
    else:
        assert acknowledged >= 0
        for item in accepted:
            assert item.seq > 0
            assert item.topology_revision == 2
            assert node_types.get(item.node_id) == item.node_type


@settings(max_examples=200, deadline=None)
@given(json_values)
def test_untrusted_selection_and_viewport_only_parse_or_raise_diagnostics(
    value: object,
) -> None:
    for parse in (
        lambda: parse_selection(value, graph()),
        lambda: parse_viewport(value),
    ):
        try:
            parse()
        except ValidationError as error:
            assert error.diagnostic.code.startswith("SGC_STATE_")


@pytest.mark.parametrize(
    "batch",
    [
        ["not an object"],
        [action(modifiers=["shift"])],
        [{k: v for k, v in action().items() if k != "target"}],
        [{**action(), "extra": True}],
    ],
    ids=["scalar", "modifiers-list", "missing-field", "extra-field"],
)
def test_action_envelope_shape_is_exact(batch: list[object]) -> None:
    with pytest.raises(ValidationError) as error:
        parse_actions(batch, graph(), topology_revision=2, acknowledged_sequence=0)
    assert error.value.diagnostic.code == "SGC_ACTION_SHAPE"


@pytest.mark.parametrize(("first", "second"), [(3, 3), (4, 3)])
def test_action_sequences_must_strictly_increase(first: int, second: int) -> None:
    with pytest.raises(ValidationError) as error:
        parse_actions(
            [action(seq=first), action(seq=second)],
            graph(),
            topology_revision=2,
            acknowledged_sequence=0,
        )
    assert error.value.diagnostic.code == "SGC_ACTION_ORDER"


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"seq": True}, "SGC_ACTION_SEQUENCE"),
        ({"topologyRevision": 0}, "SGC_ACTION_SEQUENCE"),
        ({"topologyRevision": False}, "SGC_ACTION_SEQUENCE"),
        ({"operationId": str(uuid.uuid4()).upper()}, "SGC_ACTION_OPERATION_ID"),
        ({"operationId": 7}, "SGC_ACTION_OPERATION_ID"),
        ({"target": {"kind": "edge"}}, "SGC_ACTION_GESTURE"),
        ({"nodeId": ""}, "SGC_ACTION_NODE"),
        ({"nodeType": 3}, "SGC_ACTION_NODE"),
        ({"modifiers": {"shift": False, "meta": False}}, "SGC_ACTION_MODIFIERS"),
    ],
)
def test_more_malformed_action_fields_fail_closed(
    updates: dict[str, object], code: str
) -> None:
    with pytest.raises(ValidationError) as error:
        parse_actions(
            [action(**updates)], graph(), topology_revision=2, acknowledged_sequence=0
        )
    assert error.value.diagnostic.code == code


def test_modifiers_round_trip_into_python() -> None:
    accepted, _ = parse_actions(
        [action(modifiers={"shift": True, "meta": False, "alt": True})],
        graph(),
        topology_revision=2,
        acknowledged_sequence=0,
    )
    assert (accepted[0].modifiers.shift, accepted[0].modifiers.alt) == (True, True)
    assert accepted[0].modifiers.meta is False


@pytest.mark.parametrize("zoom", [0.08, 2.5, 1])
def test_viewport_zoom_range_is_inclusive(zoom: float) -> None:
    assert parse_viewport({"x": 0, "y": 0, "zoom": zoom}) == CanvasViewport(0, 0, zoom)


@pytest.mark.parametrize("zoom", [0.0799, 2.5001, 0, -1])
def test_viewport_zoom_outside_range_fails(zoom: float) -> None:
    with pytest.raises(ValidationError) as error:
        parse_viewport({"x": 0, "y": 0, "zoom": zoom})
    assert error.value.diagnostic.code == "SGC_STATE_VIEWPORT_ZOOM"


@pytest.mark.parametrize(
    "value",
    [
        {"x": True, "y": 0, "zoom": 1},
        {"x": "0", "y": 0, "zoom": 1},
        {"x": 0, "y": 0},
        {"x": 0, "y": 0, "zoom": 1, "extra": 0},
        [0, 0, 1],
    ],
)
def test_viewport_shape_is_exact(value: object) -> None:
    with pytest.raises(ValidationError) as error:
        parse_viewport(value)
    assert error.value.diagnostic.code == "SGC_STATE_VIEWPORT"


@pytest.mark.parametrize("value", ["a", {"a": 1}, ["a", 1], ["a", ""]])
def test_selection_shape_is_exact(value: object) -> None:
    with pytest.raises(ValidationError) as error:
        parse_selection(value, graph())
    assert error.value.diagnostic.code == "SGC_STATE_SELECTION"
