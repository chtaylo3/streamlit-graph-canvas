from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml
from packaging.specifiers import SpecifierSet
from streamlit_graph_canvas.atlas import (
    ATLAS_RASTERIZER_REVISION,
    PILLOW_SUPPORTED,
)

from ci.run_compatibility import npm_specs, python_specs
from ci.sync_versions import supported_range
from ci.verify_dependency_policy import validate_policy, verify

ROOT = Path(__file__).parents[1]
FRONTEND = ROOT / "packages/core/src/streamlit_graph_canvas/frontend"
PACKAGE = json.loads((FRONTEND / "package.json").read_text())
LOCK = json.loads((FRONTEND / "package-lock.json").read_text())
POLICY = tomllib.loads((ROOT / "ci/dependency-policy.toml").read_text(encoding="utf-8"))


def test_dependency_policy_matches_project_files() -> None:
    assert verify(ROOT) == []


def test_every_declared_fixture_set_is_built_and_scheduled() -> None:
    sets = tomllib.loads((ROOT / "ci/contrib-sets.toml").read_text(encoding="utf-8"))[
        "sets"
    ]
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    wheel_runs = [
        step["run"]
        for step in workflow["jobs"]["wheels"]["steps"]
        if isinstance(step, dict) and isinstance(step.get("run"), str)
    ]
    fixture_builds = [
        command for command in wheel_runs if "ci.build_fixture_wheels" in command
    ]
    assert fixture_builds == [
        "uv run python -m ci.build_fixture_wheels --out-dir wheelhouse"
    ]
    assert not any("uv build tests/e2e/fixtures/" in command for command in wheel_runs)

    matrix_sets = workflow["jobs"]["chromium-conformance"]["strategy"]["matrix"][
        "contrib-set"
    ]
    assert len(matrix_sets) == len(set(matrix_sets))
    assert set(matrix_sets) == set(sets)


def test_pillow_policy_controls_runtime_guard_and_cache_revision() -> None:
    pillow = POLICY["python"]["Pillow"]
    assert SpecifierSet(pillow["supported"]) == PILLOW_SUPPORTED
    assert pillow["rasterizer_revision"] == ATLAS_RASTERIZER_REVISION


def test_minimum_python_stack_is_exact_and_complete() -> None:
    assert set(python_specs(POLICY, "minimum")) == {
        "streamlit==1.62.0",
        "packaging==26.0",
        "Pillow==12.3.0",
        "networkx==3.6.1",
    }


def test_python_forward_scenarios_are_isolated() -> None:
    assert python_specs(POLICY, "forward", "pillow") == ["Pillow>=13.0.0a0"]
    assert python_specs(POLICY, "forward", "streamlit") == ["streamlit>=1.62.0"]
    assert python_specs(POLICY, "forward", "supported") == []


def test_forward_frontend_scenarios_keep_coupled_packages_together() -> None:
    assert set(
        npm_specs(POLICY, "forward", "react-flow", package=PACKAGE, lock=LOCK)
    ) == {
        "react@canary",
        "react-dom@canary",
        "@types/react@^19.2.0",
        "@types/react-dom@^19.2.0",
        "@xyflow/react@next",
    }
    assert npm_specs(POLICY, "forward", "elk") == ["elkjs@next"]
    assert npm_specs(POLICY, "forward", "component") == [
        "@streamlit/component-v2-lib@next"
    ]


def test_latest_supported_uses_approved_exact_versions() -> None:
    latest = npm_specs(
        POLICY, "latest-supported", "react-flow", package=PACKAGE, lock=LOCK
    )
    assert set(latest) == {
        "react@19.2.8",
        "react-dom@19.2.8",
        "@types/react@19.2.18",
        "@types/react-dom@19.2.7",
        "@xyflow/react@12.11.6",
    }


def test_next_minor_compatibility_range_derivation() -> None:
    assert supported_range("0.2.0") == ">=0.2.0,<0.3"
    assert supported_range("0.2.4") == ">=0.2.4,<0.3"
    assert supported_range("0.3.0.dev2") == ">=0.3.0.dev2,<0.4"


def test_public_range_rejects_local_and_stable_major_versions() -> None:
    import pytest

    with pytest.raises(ValueError, match="local versions"):
        supported_range("0.2.0+local")
    with pytest.raises(ValueError, match="stable-major"):
        supported_range("1.0.0")


def test_policy_schema_rejects_unknown_and_incomplete_entries() -> None:
    import copy

    unknown = copy.deepcopy(POLICY)
    unknown["python"]["Pillow"]["typo"] = True
    assert any("unknown fields" in error for error in validate_policy(unknown))

    incomplete = copy.deepcopy(POLICY)
    del incomplete["npm"]["runtime"]["react"]["forward"]
    assert any("critical dependency" in error for error in validate_policy(incomplete))


def test_tool_upgrade_needs_no_duplicate_policy_update(monkeypatch) -> None:
    original_read = Path.read_text

    def read(path, *args, **kwargs):
        text = original_read(path, *args, **kwargs)
        if path == FRONTEND / "package.json":
            data = json.loads(text)
            data["devDependencies"]["prettier"] = "3.9.6"
            return json.dumps(data)
        if path == FRONTEND / "package-lock.json":
            data = json.loads(text)
            data["packages"][""]["devDependencies"]["prettier"] = "3.9.6"
            data["packages"]["node_modules/prettier"]["version"] = "3.9.6"
            return json.dumps(data)
        return text

    monkeypatch.setattr(Path, "read_text", read)
    assert verify(ROOT) == []


def test_supported_lanes_use_locked_tools_and_reject_duplicate_tool_endpoints() -> None:
    import copy

    lock = copy.deepcopy(LOCK)
    lock["packages"]["node_modules/prettier"]["version"] = "3.9.6"
    for lane in ("minimum", "latest-supported"):
        specs = npm_specs(POLICY, lane, "all", package=PACKAGE, lock=lock)
        assert "prettier@3.9.6" in specs
    policy = copy.deepcopy(POLICY)
    policy["npm"]["build"]["prettier"]["supported"] = "3.6.2"
    assert any("unknown fields" in error for error in validate_policy(policy))
