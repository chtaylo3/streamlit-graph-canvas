import math
import uuid

import pytest
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
