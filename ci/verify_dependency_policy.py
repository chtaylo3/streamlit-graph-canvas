"""Verify that compatibility policy matches project and CI declarations."""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

RISKS = {"critical", "high", "medium", "low"}


def _fields(
    subject: str,
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
) -> list[str]:
    errors: list[str] = []
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        errors.append(f"{subject} is missing fields: {sorted(missing)}")
    if unknown:
        errors.append(f"{subject} has unknown fields: {sorted(unknown)}")
    if value.get("risk") not in RISKS:
        errors.append(f"{subject} has invalid risk {value.get('risk')!r}")
    return errors


def validate_policy(policy: dict[str, Any]) -> list[str]:
    """Validate the closed machine-readable dependency policy schema."""

    errors: list[str] = []
    expected_top = {
        "toolchains",
        "python",
        "internal",
        "python_tooling",
        "npm",
        "ci",
    }
    if set(policy) != expected_top:
        errors.append(
            f"policy top-level fields differ: {sorted(set(policy) ^ expected_top)}"
        )
        return errors
    toolchain_fields = {
        "python_min",
        "python_locked",
        "python_forward",
        "node_locked",
        "node_supported",
        "node_forward",
        "browser",
    }
    if set(policy["toolchains"]) != toolchain_fields:
        errors.append("toolchains fields are incomplete or unknown")
    for name, entry in policy["python"].items():
        subject = f"python.{name}"
        errors.extend(
            _fields(
                subject,
                entry,
                required={"minimum", "supported", "risk", "reason", "support_url"},
                optional={"forward", "rasterizer_revision"},
            )
        )
        try:
            SpecifierSet(entry.get("supported", "not-a-specifier"))
        except Exception:
            errors.append(f"{subject} has invalid supported range")
        if entry.get("risk") == "critical" and "forward" not in entry:
            errors.append(f"{subject} critical dependency lacks a forward scenario")
    for name, entry in policy["python_tooling"].items():
        errors.extend(
            _fields(
                f"python_tooling.{name}",
                entry,
                required={"supported", "risk"},
                optional={"locked"},
            )
        )
    for name, entry in policy["internal"].items():
        errors.extend(
            _fields(
                f"internal.{name}",
                entry,
                required={"supported", "risk", "reason"},
            )
        )
    npm = policy["npm"]
    if set(npm) != {"runtime", "build", "test"}:
        errors.append("npm policy groups must be exactly runtime, build, and test")
        return errors
    npm_names = {name for group in npm.values() for name in group}
    external_couplings = {"streamlit"}
    for group, entries in npm.items():
        for name, entry in entries.items():
            subject = f"npm.{group}.{name}"
            errors.extend(
                _fields(
                    subject,
                    entry,
                    required={"minimum", "supported", "risk"},
                    optional={"forward", "coupling"},
                )
            )
            if entry.get("risk") == "critical" and "forward" not in entry:
                errors.append(f"{subject} critical dependency lacks a forward scenario")
            coupled = {
                item.strip()
                for item in str(entry.get("coupling", "")).split(",")
                if item.strip()
            }
            unknown = coupled - npm_names - external_couplings
            if unknown:
                errors.append(f"{subject} has unknown couplings: {sorted(unknown)}")
    ci_fields = {
        "blocking_lanes",
        "advisory_lanes",
        "playwright_projects",
        "required_contrib_sets",
        "release_required_workflows",
    }
    if set(policy["ci"]) != ci_fields:
        errors.append("ci policy fields are incomplete or unknown")
    return errors


def _load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _requirements(project: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    values = list(project["project"].get("dependencies", []))
    for extra in project["project"].get("optional-dependencies", {}).values():
        values.extend(extra)
    for value in values:
        requirement = Requirement(value)
        result[requirement.name] = str(requirement.specifier)
    return result


def _atlas_runtime_policy(path: Path) -> tuple[str | None, int | None]:
    """Read the guard and cache revision without importing optional runtime code."""

    supported: str | None = None
    revision: int | None = None
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id == "PILLOW_SUPPORTED" and isinstance(node.value, ast.Call):
            if (
                len(node.value.args) == 1
                and isinstance(node.value.args[0], ast.Constant)
                and isinstance(node.value.args[0].value, str)
            ):
                supported = node.value.args[0].value
        elif (
            target.id == "ATLAS_RASTERIZER_REVISION"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
        ):
            revision = node.value.value
    return supported, revision


def verify(root: Path) -> list[str]:
    policy = _load(root / "ci/dependency-policy.toml")
    core = _load(root / "packages/core/pyproject.toml")
    frontend = json.loads(
        (
            root / "packages/core/src/streamlit_graph_canvas/frontend/package.json"
        ).read_text(encoding="utf-8")
    )
    e2e = json.loads((root / "tests/e2e/package.json").read_text(encoding="utf-8"))
    frontend_lock = json.loads(
        (
            root / "packages/core/src/streamlit_graph_canvas/frontend/package-lock.json"
        ).read_text(encoding="utf-8")
    )
    e2e_lock = json.loads(
        (root / "tests/e2e/package-lock.json").read_text(encoding="utf-8")
    )
    errors: list[str] = validate_policy(policy)

    python_min = policy["toolchains"]["python_min"]
    if core["project"]["requires-python"] != f">={python_min}":
        errors.append("core requires-python differs from policy python_min")
    if (root / ".python-version").read_text(encoding="utf-8").strip() != python_min:
        errors.append(".python-version differs from policy python_min")
    declared_python = _requirements(core)
    for name, entry in policy["python"].items():
        declared = declared_python.get(name)
        if declared is None or SpecifierSet(declared) != SpecifierSet(
            entry["supported"]
        ):
            errors.append(
                f"Python {name} declares {declared_python.get(name)!r}, "
                f"policy requires {entry['supported']!r}"
            )

    runtime_supported, runtime_revision = _atlas_runtime_policy(
        root / "packages/core/src/streamlit_graph_canvas/atlas.py"
    )
    pillow_policy = policy["python"]["Pillow"]
    if runtime_supported is None or SpecifierSet(runtime_supported) != SpecifierSet(
        pillow_policy["supported"]
    ):
        errors.append("Pillow runtime guard differs from dependency policy")
    if runtime_revision != pillow_policy.get("rasterizer_revision"):
        errors.append("ATLAS rasterizer revision differs from dependency policy")

    workspace = _load(root / "pyproject.toml")
    declared_tools = _requirements(
        {
            "project": {
                "dependencies": workspace.get("dependency-groups", {}).get("dev", [])
            }
        }
    )
    build_requirement = Requirement(core["build-system"]["requires"][0])
    declared_tools[build_requirement.name] = str(build_requirement.specifier)
    for name, entry in policy["python_tooling"].items():
        declared = declared_tools.get(name)
        if declared is None or SpecifierSet(declared) != SpecifierSet(
            entry["supported"]
        ):
            errors.append(f"Python tooling {name} differs from dependency policy")

    contrib = _load(root / "packages/contrib/pyproject.toml")
    internal_requirement = Requirement(contrib["project"]["dependencies"][0])
    if SpecifierSet(str(internal_requirement.specifier)) != SpecifierSet(
        policy["internal"]["core_contrib"]["supported"]
    ):
        errors.append("core/contrib compatibility boundary differs from policy")

    frontend_declared = {
        **frontend.get("dependencies", {}),
        **frontend.get("devDependencies", {}),
    }
    for group in ("runtime", "build"):
        for name, entry in policy["npm"][group].items():
            if frontend_declared.get(name) != entry["supported"]:
                errors.append(
                    f"frontend {name} declares {frontend_declared.get(name)!r}, "
                    f"policy requires {entry['supported']!r}"
                )
    for name, entry in policy["npm"]["test"].items():
        if e2e.get("devDependencies", {}).get(name) != entry["supported"]:
            errors.append(
                f"e2e {name} declares {e2e.get('devDependencies', {}).get(name)!r}, "
                f"policy requires {entry['supported']!r}"
            )

    for label, package, lock in (
        ("frontend", frontend, frontend_lock),
        ("e2e", e2e, e2e_lock),
    ):
        locked_root = lock.get("packages", {}).get("", {})
        for group in ("dependencies", "devDependencies"):
            if package.get(group, {}) != locked_root.get(group, {}):
                errors.append(f"{label} package-lock root {group} is stale")
        expected_engine = policy["toolchains"]["node_supported"]
        if package.get("engines", {}).get("node") != expected_engine:
            errors.append(f"{label} Node engine differs from policy")
        if locked_root.get("engines", {}).get("node") != expected_engine:
            errors.append(f"{label} package-lock Node engine is stale")

    uv_names = {
        item["name"].casefold() for item in _load(root / "uv.lock").get("package", [])
    }
    for name in policy["python"]:
        if name.casefold() not in uv_names:
            errors.append(f"Python {name} is absent from uv.lock")

    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for version in policy["toolchains"]["python_locked"]:
        if f'"{version}"' not in ci:
            errors.append(f"locked Python {version} is absent from CI")
    node = policy["toolchains"]["node_locked"]
    if not re.search(rf"node-version:\s*[\"']?{re.escape(node)}", ci):
        errors.append(f"locked Node {node} is absent from CI")
    contrib_sets = _load(root / "ci/contrib-sets.toml")["sets"]
    expected_sets = set(policy["ci"]["required_contrib_sets"])
    if set(contrib_sets) != expected_sets:
        errors.append(
            f"contrib sets {sorted(contrib_sets)} differ from policy "
            f"{sorted(expected_sets)}"
        )
    playwright = (root / "tests/e2e/playwright.config.ts").read_text(encoding="utf-8")
    for project in policy["ci"]["playwright_projects"]:
        if f'name: "{project}"' not in playwright:
            errors.append(f"Playwright project {project!r} is not configured")
    required_artifacts = (
        "packages/core/THIRD_PARTY_LICENSES.md",
        "packages/core/src/streamlit_graph_canvas/frontend/build/bundled-packages.json",
        "packages/core/src/streamlit_graph_canvas/frontend/build/third-party-licenses.json",
    )
    for relative in required_artifacts:
        if not (root / relative).is_file():
            errors.append(f"required bundle or license artifact is absent: {relative}")

    workflows = list((root / ".github/workflows").glob("*.yml"))
    for workflow in workflows:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = re.search(r"uses:\s*[^@\s]+@([^\s#]+)", line)
            if match and not re.fullmatch(r"[0-9a-f]{40}", match.group(1)):
                errors.append(f"GitHub Action is not pinned by SHA in {workflow.name}")
    prerelease = (root / ".github/workflows/prerelease-compatibility.yml").read_text(
        encoding="utf-8"
    )
    for scenario in (
        "python-forward",
        "scenario: pillow",
        "react-flow",
        "elk",
        "component",
        "chrome-beta",
    ):
        if scenario not in prerelease:
            errors.append(f"forward workflow lacks {scenario!r} scenario")
    release = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    if (
        "cp dist/*.whl conformance-wheelhouse/" not in release
        or "--constraints locked-constraints.txt" not in release
    ):
        errors.append("release verification does not test its built dist wheels")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    errors = verify(args.root)
    if errors:
        raise SystemExit("dependency policy violations:\n- " + "\n- ".join(errors))
    print("dependency policy is consistent")


if __name__ == "__main__":
    main()
