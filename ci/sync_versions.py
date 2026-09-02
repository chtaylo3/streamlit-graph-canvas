"""Synchronize metadata that must repeat the workspace release version."""

from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from packaging.version import Version

from .fixture_inventory import discover_fixture_projects


@dataclass(frozen=True)
class VersionTarget:
    path: str
    pattern: str
    replacement: str


def workspace_version(root: Path) -> str:
    """Return the authoritative version from the workspace project metadata."""
    raw = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = raw["project"]["version"]
    Version(version)
    return version


def supported_range(version: str) -> str:
    parsed = Version(version)
    if parsed.local is not None:
        raise ValueError("local versions cannot define a public compatibility range")
    if parsed.major != 0:
        raise ValueError(
            "stable-major releases require an explicit compatibility policy"
        )
    return f">={version},<0.{parsed.minor + 1}"


def contrib_javascript_targets(version: str, root: Path) -> tuple[VersionTarget, ...]:
    """Return version targets embedded in shipped contrib JavaScript assets."""
    manifest = (
        root / "packages/contrib/src/streamlit_graph_canvas_contrib/renderer.toml"
    )
    if not manifest.is_file():
        return ()
    raw = tomllib.loads(manifest.read_text(encoding="utf-8"))
    assets = {
        renderer["javascript"]
        for renderer in raw.get("renderers", [])
        if isinstance(renderer, dict) and "javascript" in renderer
    }
    if not assets:
        return ()
    return tuple(
        VersionTarget(
            (manifest.parent / relative).relative_to(root).as_posix(),
            r'(?m)^(\s+version: ")[^"]+(",\s*)$',
            rf"\g<1>{version}\g<2>",
        )
        for relative in sorted(assets)
    )


def targets(version: str, root: Path) -> tuple[VersionTarget, ...]:
    compatibility = supported_range(version)
    return (
        VersionTarget(
            "packages/core/pyproject.toml",
            r'(?m)^(version = ")[^"]+("\s*)$',
            rf"\g<1>{version}\g<2>",
        ),
        VersionTarget(
            "packages/core/src/streamlit_graph_canvas/pyproject.toml",
            r'(?m)^(version = ")[^"]+("\s*)$',
            rf"\g<1>{version}\g<2>",
        ),
        VersionTarget(
            "packages/contrib/pyproject.toml",
            r'(?m)^(version = ")[^"]+("\s*)$',
            rf"\g<1>{version}\g<2>",
        ),
        VersionTarget(
            "packages/contrib/pyproject.toml",
            r'(?m)^(dependencies = \["streamlit-graph-canvas)[^"]+(")',
            rf"\g<1>{compatibility}\g<2>",
        ),
        VersionTarget(
            "packages/contrib/src/streamlit_graph_canvas_contrib/pyproject.toml",
            r'(?m)^(version = ")[^"]+("\s*)$',
            rf"\g<1>{version}\g<2>",
        ),
        VersionTarget(
            "packages/contrib/src/streamlit_graph_canvas_contrib/renderer.toml",
            r'(?m)^(version = ")[^"]+("\s*)$',
            rf"\g<1>{version}\g<2>",
        ),
        *contrib_javascript_targets(version, root),
        *(
            VersionTarget(
                f"{fixture}/pyproject.toml",
                r'(?m)^(dependencies = \["streamlit-graph-canvas)[^"]+(")',
                rf"\g<1>{compatibility}\g<2>",
            )
            for fixture in (
                project.relative_path.as_posix()
                for project in discover_fixture_projects(root)
            )
        ),
        VersionTarget(
            "ci/dependency-policy.toml",
            (
                r'(?m)^(supported = ")[^"]+("\s*\nrisk = "critical"'
                r'\s*\nreason = "Pre-1.0 renderer API)'
            ),
            rf"\g<1>{compatibility}\g<2>",
        ),
    )


def synchronize(root: Path, *, write: bool) -> list[str]:
    """Return stale paths, optionally rewriting their derived version fields."""
    version = workspace_version(root)
    stale: list[str] = []
    javascript_updated = False
    for target in targets(version, root):
        path = root / target.path
        original = path.read_text(encoding="utf-8")
        updated, count = re.subn(target.pattern, target.replacement, original, count=1)
        if count != 1:
            raise SystemExit(f"version field not found exactly once in {target.path}")
        if updated == original:
            continue
        stale.append(target.path)
        if write:
            path.write_text(updated, encoding="utf-8")
            javascript_updated = javascript_updated or path.suffix == ".js"
    if javascript_updated:
        # The embedded version participates in the renderer build identity and
        # content-addressed filename. Refresh both after rewriting the source.
        from .sync_renderer_assets import synchronize as synchronize_assets

        synchronize_assets(root, write=True)
    return stale


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail on stale metadata")
    mode.add_argument("--write", action="store_true", help="update stale metadata")
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    stale = synchronize(args.root, write=args.write)
    if stale and not args.write:
        joined = "\n  - ".join(stale)
        raise SystemExit(
            "derived versions do not match pyproject.toml; run "
            f"`uv run python -m ci.sync_versions --write`:\n  - {joined}"
        )
    if args.write and stale:
        print(f"synchronized {len(stale)} version fields")


if __name__ == "__main__":
    main()
