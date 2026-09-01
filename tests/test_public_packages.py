from importlib.metadata import version

import streamlit_graph_canvas
import streamlit_graph_canvas_contrib


def test_distributions_are_importable() -> None:
    assert streamlit_graph_canvas.__version__ == version("streamlit-graph-canvas")
    assert streamlit_graph_canvas_contrib.__version__ == version(
        "streamlit-graph-canvas-contrib"
    )
