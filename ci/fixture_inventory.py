"""Discover independently built E2E fixture projects without importing them."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_NORMALIZE = re.compile(r"[-_.]+")


@dataclass(frozen=True, slots=True)
class FixtureProject:
    path: Path
    relative_path: Path
    name: str
    normalized_name: str


def normalize_distribution_name(name: str) -> str:
    """Return the canonical comparison form used by Python distributions."""

    return _NORMALIZE.sub("-", name).lower()


def discover_fixture_projects(root: Path) -> tuple[FixtureProject, ...]:
    """Return validated immediate-child fixture projects in stable path order."""

    repository = root.resolve()
    fixture_root = (repository / "tests/e2e/fixtures").resolve()
    if not fixture_root.is_dir() or not fixture_root.is_relative_to(repository):
        raise ValueError(
            f"fixture root is missing or escapes repository: {fixture_root}"
        )

    projects: list[FixtureProject] = []
    seen: dict[str, Path] = {}
    for child in sorted(fixture_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        project = child / "pyproject.toml"
        resolved_child = child.resolve()
        if not resolved_child.is_relative_to(fixture_root) or resolved_child != child:
            raise ValueError(
                f"fixture directory must not escape through a link: {child}"
            )
        if not project.is_file():
            raise ValueError(f"fixture project is missing pyproject.toml: {child}")
        try:
            raw = tomllib.loads(project.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            raise ValueError(
                f"invalid fixture project metadata: {project}: {error}"
            ) from error
        name = raw.get("project", {}).get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"fixture project has no non-empty [project].name: {project}"
            )
        normalized = normalize_distribution_name(name)
        previous = seen.get(normalized)
        if previous is not None:
            raise ValueError(
                f"duplicate normalized fixture name {normalized!r}: "
                f"{previous} and {project}"
            )
        seen[normalized] = project
        projects.append(
            FixtureProject(
                path=resolved_child,
                relative_path=resolved_child.relative_to(repository),
                name=name,
                normalized_name=normalized,
            )
        )
    return tuple(projects)
