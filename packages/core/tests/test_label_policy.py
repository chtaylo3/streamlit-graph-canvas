import pytest
from streamlit_graph_canvas import (
    GraphData,
    GraphSchema,
    LabelPolicy,
    Node,
    NodeType,
    serialize_graph,
)


def test_defaults_type_overrides_and_compact_label_preserve_original():
    default = LabelPolicy(layout="wrap", lines=3)
    single = LabelPolicy(layout="single", lines=1, ellipsis="middle")
    schema = GraphSchema(
        {"a": NodeType("a"), "b": NodeType("b", label_policy=single)},
        {},
        label_policy=default,
    )
    graph = GraphData(
        (
            Node("1", "a", "original/full-name.txt", display_label="short.txt"),
            Node("2", "b", "another"),
        ),
        (),
    )
    serialized = serialize_graph(schema, graph)
    assert (
        serialized.envelope["schema"]["nodeTypes"]["a"]["labelPolicy"]["layout"]
        == "wrap"
    )
    assert (
        serialized.envelope["schema"]["nodeTypes"]["b"]["labelPolicy"]["layout"]
        == "single"
    )
    assert (
        serialized.envelope["presentation"]["nodes"][0]["label"]
        == "original/full-name.txt"
    )
    assert (
        serialized.envelope["presentation"]["nodes"][0]["displayLabel"] == "short.txt"
    )


@pytest.mark.parametrize(
    "options",
    [
        {"layout": "grow"},
        {"layout": "single"},
        {"layout": "path", "lines": 3},
        {"layout": "wrap", "ellipsis": "middle"},
        {"lines": 0},
        {"lines": True},
        {"font_size": 0},
        {"min_font_size": 15},
        {"min_font_size": True},
        {"reveal_hover": "yes"},
        {"ellipsis": "clip"},
        {"reveal_mode": "bad"},
        {"reveal_delay_ms": -1},
        {"reveal_delay_ms": True},
        {"reveal_delay_ms": 2**31},
        {"reveal_focus": True},
        {"reveal_button": True},
    ],
)
def test_incompatible_label_options_fail_at_configuration(options):
    with pytest.raises(ValueError, match="LabelPolicy"):
        LabelPolicy(**options)


def test_invalid_policy_objects_fail_at_configuration():
    with pytest.raises(ValueError, match="label_policy"):
        GraphSchema({}, {}, label_policy={})
    with pytest.raises(ValueError, match="label_policy"):
        NodeType("x", label_policy={})
