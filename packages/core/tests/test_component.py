from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_basic_example_mounts_without_python_error() -> None:
    example = Path(__file__).parents[3] / "examples" / "basic.py"
    app = AppTest.from_file(str(example), default_timeout=20).run()
    assert not app.exception


def test_transition_options_reject_invalid_values_before_mount() -> None:
    import pytest
    from streamlit_graph_canvas import GraphData, GraphSchema, graph_canvas

    for duration in (-1, 1001, True, 2.5):
        with pytest.raises(ValueError, match="transition_ms"):
            graph_canvas(
                GraphData((), ()),
                GraphSchema({}, {}),
                key="motion",
                transition_ms=duration,
            )
    with pytest.raises(ValueError, match="navigation_anchor"):
        graph_canvas(
            GraphData((), ()), GraphSchema({}, {}), key="motion", navigation_anchor=42
        )


def test_display_budget_is_separate_from_input_limit() -> None:
    source = (Path(__file__).parents[3] / "examples" / "basic.py").read_text()
    # Five input elements are accepted even though only two can be drawn.
    source = source.replace(
        'key="basic-graph"', 'key="basic-graph", max_elements=2, max_loaded_elements=10'
    )
    assert not AppTest.from_string(source, default_timeout=20).run().exception
    rejected = AppTest.from_string(
        source.replace("max_loaded_elements=10", "max_loaded_elements=4"),
        default_timeout=20,
    ).run()
    assert rejected.exception
    assert "4-element budget" in rejected.exception[0].message


def test_element_budgets_require_positive_integers() -> None:
    import pytest
    from streamlit_graph_canvas import GraphData, GraphSchema, graph_canvas

    for name in ("max_elements", "max_loaded_elements"):
        for value in (0, -1, True, 2.5):
            with pytest.raises(ValueError, match=name):
                graph_canvas(
                    GraphData((), ()),
                    GraphSchema({}, {}),
                    key="budget",
                    **{name: value},
                )
