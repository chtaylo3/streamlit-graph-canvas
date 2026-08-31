"""Stock renderers for Streamlit Graph Canvas."""

from importlib.resources import files
from pathlib import Path

__all__ = ["renderer_manifest"]
__version__ = "0.1.0.dev0"


def renderer_manifest() -> Path:
    """Return the static manifest without importing renderer implementations."""

    return Path(str(files(__package__).joinpath("renderer.toml")))
