from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_basic_example_mounts_without_python_error() -> None:
    example = Path(__file__).parents[3] / "examples" / "basic.py"
    app = AppTest.from_file(str(example), default_timeout=20).run()
    assert not app.exception
