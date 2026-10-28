import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from streamlit_graph_canvas import GraphData, Node, SearchField
from streamlit_graph_canvas.search import parse_search_request


@pytest.fixture
def request_data():
    return {
        "query": "requests",
        "criteria": [{"field": "high", "operator": "gt", "value": 2}],
        "matchMode": "all",
        "includeContext": False,
        "matchingNodeIds": ["a"],
        "sequence": 1,
        "topologyRevision": 2,
        "presentationRevision": 3,
    }


def parse(raw, acknowledged=0):
    return parse_search_request(
        raw,
        GraphData((Node("a", "package", "requests"),), ()),
        (SearchField("high", "High findings", "number"),),
        topology_revision=2,
        presentation_revision=3,
        acknowledged=acknowledged,
    )


def test_explicit_request_validation_and_replay(request_data):
    result = parse(request_data)
    assert result is not None
    assert result.matching_node_ids == ("a",)
    assert result.criteria[0].value == 2
    assert parse(request_data, acknowledged=1) is None
    assert parse(request_data | {"topologyRevision": 1}) is None
    assert parse(request_data | {"presentationRevision": 1}) is None
    assert parse(request_data | {"matchingNodeIds": ["missing"]}) is None


def test_malformed_search_requests_are_ignored(request_data):
    for value in (
        None,
        [],
        True,
        "bad",
        request_data | {"matchMode": []},
        request_data | {"criteria": [{}]},
        request_data | {"sequence": True},
        request_data
        | {"criteria": [{"field": "high", "operator": "gt", "value": float("nan")}]},
        request_data
        | {"criteria": [{"field": "high", "operator": "gt", "value": True}]},
    ):
        assert parse(value) is None


def test_field_definitions_validate_types():
    for values in (
        {"key": "$label", "label": "Bad"},
        {"key": "", "label": "Bad"},
        {"key": "x", "label": "X", "kind": "choice"},
    ):
        with pytest.raises(ValueError):
            SearchField(**values)


def test_search_options_validate_before_mount():
    from streamlit_graph_canvas import GraphSchema, graph_canvas

    for name, invalid in (
        ("search_reorder_threshold", (0, -1, True, 2.5)),
        ("search_nonmatch_opacity", (-1, 2, True, float("nan"))),
        ("search_fields", ([], (SearchField("a", "A"), SearchField("a", "A")))),
        ("search_active_ids", (("missing",),)),
        ("on_search_request", (lambda: None,)),
    ):
        for value in invalid:
            with pytest.raises(ValueError, match=name):
                graph_canvas(
                    GraphData((), ()),
                    GraphSchema({}, {}),
                    key="invalid",
                    **{name: value},
                )


_json = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(max_size=10), children, max_size=4)
    ),
    max_leaves=20,
)
_REQUEST_FIELDS = [
    "query",
    "criteria",
    "matchMode",
    "includeContext",
    "matchingNodeIds",
    "sequence",
    "topologyRevision",
    "presentationRevision",
]


@settings(max_examples=300, deadline=None)
@given(
    st.dictionaries(st.sampled_from(_REQUEST_FIELDS), _json, max_size=4),
    st.lists(
        st.fixed_dictionaries(
            {},
            optional={
                "field": st.sampled_from(["high", "$label", "nope"]) | _json,
                "operator": st.sampled_from(["eq", "gt", "contains", "known"]) | _json,
                "value": _json,
            },
        ),
        max_size=3,
    ),
)
def test_untrusted_search_requests_never_raise(
    overrides: dict[str, object], criteria: list[dict[str, object]]
) -> None:
    raw = {
        "query": "requests",
        "criteria": criteria,
        "matchMode": "all",
        "includeContext": False,
        "matchingNodeIds": ["a"],
        "sequence": 1,
        "topologyRevision": 2,
        "presentationRevision": 3,
    } | overrides
    result = parse(raw)
    if result is not None:
        assert set(result.matching_node_ids) <= {"a"}
        assert all(item.field in {"high", "$label"} for item in result.criteria)
