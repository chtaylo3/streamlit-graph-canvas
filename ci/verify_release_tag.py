"""Require a release tag to identify the exact source-tree project version."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from packaging.version import Version


def verify_release_tag(tag: str, root: Path) -> None:
    """Validate that *tag* identifies a publishable source-tree version."""
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    parsed = Version(version)
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(
            f"release tag {tag!r} does not match project version {expected!r}"
        )
    if parsed.is_devrelease:
        raise ValueError(
            f"development version {version!r} may be built by CI but not published"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    try:
        verify_release_tag(args.tag, args.root)
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
