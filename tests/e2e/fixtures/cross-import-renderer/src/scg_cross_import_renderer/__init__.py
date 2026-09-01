"""Static fixture whose manifest attempts to import another distribution."""

from importlib.resources import files
from pathlib import Path


def renderer_manifest() -> Path:
    return Path(str(files(__package__).joinpath("renderer.toml")))
