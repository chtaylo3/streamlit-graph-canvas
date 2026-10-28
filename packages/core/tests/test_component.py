from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from streamlit_graph_canvas.component import _browser_atlas_state, _revision_state

PAGE = "a" * 64


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


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (SimpleNamespace(), ("light", 1.0, [])),
        (
            SimpleNamespace(
                atlas_theme="dark", atlas_resolution=1.25, atlas_page_ids=[PAGE]
            ),
            ("dark", 1.5, [PAGE]),
        ),
        (SimpleNamespace(atlas_theme="sepia"), ("light", 1.0, [])),
        (SimpleNamespace(atlas_theme=["dark"]), ("light", 1.0, [])),
        (SimpleNamespace(atlas_theme={"dark": 1}), ("light", 1.0, [])),
        (SimpleNamespace(atlas_resolution=True), ("light", 1.0, [])),
        (SimpleNamespace(atlas_resolution="2"), ("light", 1.0, [])),
        (SimpleNamespace(atlas_resolution=float("nan")), ("light", 2.0, [])),
        (SimpleNamespace(atlas_resolution=1e308), ("light", 2.0, [])),
        (SimpleNamespace(atlas_resolution=-5), ("light", 1.0, [])),
        (SimpleNamespace(atlas_page_ids=[PAGE, PAGE]), ("light", 1.0, [PAGE])),
        (SimpleNamespace(atlas_page_ids=[PAGE[:-1]]), ("light", 1.0, [])),
        (SimpleNamespace(atlas_page_ids=[PAGE, 7]), ("light", 1.0, [])),
        (SimpleNamespace(atlas_page_ids=(PAGE,)), ("light", 1.0, [])),
        (SimpleNamespace(atlas_page_ids=[PAGE] * 513), ("light", 1.0, [])),
    ],
)
def test_browser_atlas_state_is_sanitized(result: object, expected: tuple) -> None:
    sanitized = _browser_atlas_state(result)
    assert sanitized == expected
    # Idempotent: feeding sanitized state back cannot trigger another
    # theme/resolution rerun, so hostile browser values cannot loop.
    theme, resolution, pages = sanitized
    again = SimpleNamespace(
        atlas_theme=theme, atlas_resolution=resolution, atlas_page_ids=pages
    )
    assert _browser_atlas_state(again) == sanitized


def test_revision_state_bumps_only_changed_hashes_and_fills_legacy_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit

    session: dict[str, object] = {}
    monkeypatch.setattr(streamlit, "session_state", session)
    first = _revision_state("k", "topo-1", "pres-1")
    assert (first["topology_revision"], first["presentation_revision"]) == (1, 1)
    same = _revision_state("k", "topo-1", "pres-1")
    assert (same["topology_revision"], same["presentation_revision"]) == (1, 1)
    restyled = _revision_state("k", "topo-1", "pres-2")
    assert (restyled["topology_revision"], restyled["presentation_revision"]) == (1, 2)
    moved = _revision_state("k", "topo-2", "pres-2")
    assert (moved["topology_revision"], moved["presentation_revision"]) == (2, 2)
    # Session state written by an older release lacks newer fields.
    session["_sgc:legacy"] = {
        "topology_hash": "t",
        "presentation_hash": "p",
        "topology_revision": 4,
        "presentation_revision": 9,
    }
    legacy = _revision_state("legacy", "t", "p")
    assert legacy["topology_revision"] == 4
    assert legacy["selected_node_ids"] == []
    assert legacy["viewport"] is None
    assert legacy["acknowledged_sequence"] == 0
    assert legacy["search_acknowledged_sequence"] == 0
    assert (legacy["atlas_theme"], legacy["atlas_resolution"]) == ("light", 1.0)
    assert legacy["atlas_page_ids"] == []
    # Keys are isolated per canvas.
    assert _revision_state("other", "topo-9", "pres-9")["topology_revision"] == 1
