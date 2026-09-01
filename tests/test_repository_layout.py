from __future__ import annotations

import shlex
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _is_ignored(relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", relative],
        cwd=ROOT,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise AssertionError(
            f"git check-ignore failed for {relative!r} with {result.returncode}"
        )
    return result.returncode == 0


def test_root_build_output_families_are_ignored_without_inner_rules() -> None:
    paths = (
        "wheelhouse/package.whl",
        "wheelhouse-beta/package.tar.gz",
        "build-wheelhouse/backend.whl",
        "conformance-wheelhouse/fixture.whl",
        "compatibility-wheelhouse/core.whl",
        "forward-wheelhouse/core.whl",
        "forward-stack-wheelhouse/core.whl",
        "direct-dist/release.tar.gz",
    )
    unprotected = [path for path in paths if not _is_ignored(path)]
    assert unprotected == [], f"root build outputs are not ignored: {unprotected}"


def test_archives_are_not_ignored_globally_by_extension() -> None:
    path = "tests/e2e/fixtures/archive-policy/payload.tar.gz"
    assert not _is_ignored(path), f"non-output archive is unexpectedly ignored: {path}"


def test_pytest_excludes_only_the_explicit_e2e_path() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]
    options = shlex.split(pytest_config["addopts"])
    assert "--ignore=tests/e2e/" in options
    assert "norecursedirs" not in pytest_config
    assert pytest_config["pythonpath"] == ["."]
