"""Validate build-backend updates against an explicitly approved policy range."""

from __future__ import annotations

import copy
import re

BUILD_MANIFESTS = frozenset(
    {"packages/core/pyproject.toml", "packages/contrib/pyproject.toml"}
)


def _version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", value):
        raise ValueError("build versions must be stable numeric releases")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (3 - len(parts))


def _bounds(specifiers: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    # The publisher uses only the standard library. Deliberately reject other
    # PEP 440 shapes rather than approximating arbitrary specifier containment.
    bounds = {}
    for specifier in specifiers.split(","):
        match = re.fullmatch(r"\s*(>=|<)\s*([0-9.]+)\s*", specifier)
        if match is None or match[1] in bounds:
            raise ValueError("expected one minimum and one upper bound")
        bounds[match[1]] = _version(match[2])
    if set(bounds) != {">=", "<"}:
        raise ValueError("expected an inclusive minimum and exclusive upper bound")
    if bounds[">="] >= bounds["<"]:
        raise ValueError("empty build requirement range")
    return bounds[">="], bounds["<"]


def build_requirement_allowed(requirement: str, policy: dict) -> bool:
    """Keep the approved minimum and build pin, allowing a narrower upper bound."""
    try:
        match = re.fullmatch(r"uv[-_]build\s*((?:>=|<).+)", requirement, re.IGNORECASE)
        if match is None:
            return False
        minimum, upper = _bounds(match[1])
        approved_minimum, approved_upper = _bounds(policy["supported"])
        pinned = _version(policy["locked"])
        return (
            minimum == approved_minimum
            and upper <= approved_upper
            and minimum <= pinned < upper
        )
    except (KeyError, TypeError, ValueError):
        return False


def validate_build_manifest(base: dict, candidate: dict, policy: dict) -> None:
    """Only an approved uv_build requirement may change in a package manifest."""
    build = candidate.get("build-system", {})
    requirements = build.get("requires")
    if (
        build.get("build-backend") != "uv_build"
        or "backend-path" in build
        or not isinstance(requirements, list)
        or len(requirements) != 1
        or not isinstance(requirements[0], str)
        or not build_requirement_allowed(requirements[0], policy)
    ):
        raise ValueError("build requirement requires explicit policy review")
    expected = copy.deepcopy(base)
    expected.setdefault("build-system", {})["requires"] = requirements
    if candidate != expected:
        raise ValueError("only build-system.requires may change without review")
