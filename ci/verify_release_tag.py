"""Require a release tag to identify the exact source-tree project version."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from packaging.version import Version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    version = tomllib.loads((args.root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    expected = f"v{version}"
    if args.tag != expected:
        raise SystemExit(
            f"release tag {args.tag!r} does not match project version {expected!r}"
        )
    # Parse explicitly so malformed versions never reach the publisher.
    Version(version)


if __name__ == "__main__":
    main()
