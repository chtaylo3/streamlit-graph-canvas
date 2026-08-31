from pathlib import Path

from streamlit_graph_canvas_contrib import renderer_manifest


def test_static_renderer_manifest_is_packaged() -> None:
    path = renderer_manifest()
    assert isinstance(path, Path)
    assert path.name == "renderer.toml"
    assert path.is_file()
