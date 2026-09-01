"""Never imported: the fixture exists to exercise static discovery failures."""

from importlib.resources import files
from pathlib import Path


def renderer_manifest() -> Path:
    return Path(str(files(__package__).joinpath("renderer.toml")))
