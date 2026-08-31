import streamlit_graph_canvas
import streamlit_graph_canvas_contrib


def test_distributions_are_importable() -> None:
    assert streamlit_graph_canvas.__version__.startswith("0.1.0")
    assert streamlit_graph_canvas_contrib.__version__.startswith("0.1.0")
