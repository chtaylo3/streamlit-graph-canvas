from __future__ import annotations

import base64
import copy
import json
import tomllib

import pytest

from ci.build_requirements import (
    BUILD_MANIFESTS,
    build_requirement_allowed,
    validate_build_manifest,
)
from ci.prepare_dependency_pr import allowed_output, prepare
from ci.publish_dependency_pr import verify_build_manifest_inputs

POLICY = {"supported": ">=0.12.6,<0.14", "locked": "0.12.6"}
BASE = """[build-system]
requires = ["uv_build>=0.12.6,<0.13"]
build-backend = "uv_build"

[project]
name = "sample"
dependencies = ["streamlit>=1.66.1"]
"""
CANDIDATE = BASE.replace("<0.13", "<0.14")
POLICY_TOML = """[python_tooling.uv_build]
supported = ">=0.12.6,<0.14"
locked = "0.12.6"
"""


@pytest.mark.parametrize(
    ("requirement", "allowed"),
    [
        ("uv_build>=0.12.6,<0.13", True),
        ("uv_build>=0.12.6,<0.14", True),
        ("uv-build<0.14,>=0.12.6", True),
        ("uv_build>=0.12.6,<0.15", False),
        ("uv_build>=0.12.5,<0.14", False),
        ("uv_build>=0.13,<0.14", False),
        ("uv_build>=0.12.6,<0.12.6", False),
        ("uv_build>=0.12.6", False),
        ("uv_build==0.13.6", False),
        ("uv_build>=0.12.6,<=0.14", False),
        ("uv_build>=0.12.6,<0.14rc1", False),
        ("uv_build>=0.12.6,<0.14.dev1", False),
        ("uv_build>=0.12.6,<0.14+local", False),
        ("uv_build>=0.12.6,<0.14,!=0.13.0", False),
        ("uv_build @ https://example.com/backend.whl", False),
        ("uv_build[extra]>=0.12.6,<0.14", False),
        ('uv_build>=0.12.6,<0.14; python_version >= "3.12"', False),
        ("other_backend>=0.12.6,<0.14", False),
    ],
)
def test_build_range_preserves_approved_minimum_upper_bound_and_pin(
    requirement, allowed
) -> None:
    assert build_requirement_allowed(requirement, POLICY) is allowed
    assert not build_requirement_allowed(requirement, {**POLICY, "locked": "0.15"})


@pytest.mark.parametrize(
    "alter", ["backend", "backend_path", "requires", "runtime", "version", "sources"]
)
def test_build_manifest_update_cannot_change_other_project_fields(alter) -> None:
    base = tomllib.loads(BASE)
    candidate = tomllib.loads(CANDIDATE)
    validate_build_manifest(base, candidate, POLICY)
    changed = copy.deepcopy(candidate)
    if alter == "backend":
        changed["build-system"]["build-backend"] = "attacker"
    elif alter == "backend_path":
        changed["build-system"]["backend-path"] = ["."]
    elif alter == "requires":
        changed["build-system"]["requires"].append("attacker")
    elif alter == "runtime":
        changed["project"]["dependencies"] = ["attacker"]
    elif alter == "version":
        changed["project"]["version"] = "99.0.0"
    else:
        changed["tool"] = {"uv": {"sources": {"streamlit": {"path": "../trusted"}}}}
    with pytest.raises(ValueError, match="review"):
        validate_build_manifest(base, changed, POLICY)


@pytest.mark.parametrize("manifest", sorted(BUILD_MANIFESTS))
def test_preparation_accepts_approved_build_input_without_generating_manifest(
    tmp_path, monkeypatch, manifest
) -> None:
    path = tmp_path / manifest
    path.parent.mkdir(parents=True)
    path.write_text(CANDIDATE)
    calls = {
        ("show", "base:ci/dependency-policy.toml"): POLICY_TOML.encode(),
        ("show", f"base:{manifest}"): BASE.encode(),
        ("diff", "--name-only", "base", "head"): manifest.encode(),
        ("diff", "--name-only", "head"): b"",
        ("ls-files", "--others", "--exclude-standard"): b"",
    }
    monkeypatch.setattr("ci.prepare_dependency_pr.git", lambda root, *args: calls[args])
    output = tmp_path / "prepared.json"
    prepare(tmp_path, "base", "head", output)
    assert json.loads(output.read_text())["files"] == []
    assert path.read_text() == CANDIDATE
    assert not allowed_output(manifest)

    path.write_text(CANDIDATE.replace("<0.14", "<0.15"))
    with pytest.raises(ValueError, match="policy review"):
        prepare(tmp_path, "base", "head", output)


@pytest.mark.parametrize("manifest", sorted(BUILD_MANIFESTS))
def test_publisher_independently_rechecks_build_inputs(monkeypatch, manifest) -> None:
    candidate = CANDIDATE

    def api(path):
        if "ci/dependency-policy.toml" in path:
            content = POLICY_TOML
        else:
            content = BASE if path.endswith("ref=base") else candidate
        return {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(content.encode()).decode(),
        }

    monkeypatch.setattr("ci.publish_dependency_pr.api", api)
    pr = {"base": {"sha": "base"}, "head": {"sha": "head"}}
    verify_build_manifest_inputs("owner/repo", pr, {manifest})
    candidate = CANDIDATE.replace("<0.14", "<0.15")
    with pytest.raises(ValueError, match="policy review"):
        verify_build_manifest_inputs("owner/repo", pr, {manifest})
    candidate = CANDIDATE.replace('name = "sample"', 'name = "attacker"')
    with pytest.raises(ValueError, match=r"only build-system\.requires"):
        verify_build_manifest_inputs("owner/repo", pr, {manifest})
