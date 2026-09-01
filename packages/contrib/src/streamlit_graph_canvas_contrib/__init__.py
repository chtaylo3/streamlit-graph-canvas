"""Stock renderers for Streamlit Graph Canvas."""

from importlib.metadata import version as distribution_version
from importlib.resources import files
from pathlib import Path

__all__ = ["renderer_manifest"]
__version__ = distribution_version("streamlit-graph-canvas-contrib")


def renderer_manifest() -> Path:
    """Return the static manifest without importing renderer implementations."""

    return Path(str(files(__package__).joinpath("renderer.toml")))
