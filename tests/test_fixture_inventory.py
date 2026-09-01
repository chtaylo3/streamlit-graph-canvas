from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ci.build_conformance_environment import validate_set_coverage
from ci.build_fixture_wheels import build_fixture_wheels
from ci.fixture_inventory import discover_fixture_projects
from ci.sync_versions import targets

ROOT = Path(__file__).parents[1]


def _fixture(root: Path, directory: str, name: str = "example-fixture") -> Path:
    path = root / "tests/e2e/fixtures" / directory
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return path


def test_repository_fixture_inventory_is_stable_and_immediate_child_only() -> None:
    fixtures = discover_fixture_projects(ROOT)
    assert len(fixtures) == 8
    assert [item.relative_path.as_posix() for item in fixtures] == sorted(
        item.relative_path.as_posix() for item in fixtures
    )
    assert all(item.path.parent.name == "fixtures" for item in fixtures)


def test_nested_component_manifest_is_not_a_fixture_project(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, "outer")
    nested = fixture / "src/package"
    nested.mkdir(parents=True)
    (nested / "pyproject.toml").write_text(
        '[project]\nname = "nested-component"\n', encoding="utf-8"
    )
    inventory = discover_fixture_projects(tmp_path)
    assert [item.name for item in inventory] == ["example-fixture"]


def test_fixture_directory_without_project_manifest_fails_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests/e2e/fixtures/missing").mkdir(parents=True)
    with pytest.raises(ValueError, match=r"missing pyproject\.toml"):
        discover_fixture_projects(tmp_path)


@pytest.mark.parametrize(
    "metadata",
    (
        "not = [valid TOML",
        '[project]\nversion = "0.1.0"\n',
        '[project]\nname = ""\n',
    ),
)
def test_invalid_fixture_project_name_fails_closed(
    tmp_path: Path, metadata: str
) -> None:
    fixture = _fixture(tmp_path, "broken")
    (fixture / "pyproject.toml").write_text(metadata, encoding="utf-8")
    with pytest.raises(ValueError, match="fixture project"):
        discover_fixture_projects(tmp_path)


def test_duplicate_normalized_fixture_names_report_both_paths(tmp_path: Path) -> None:
    first = _fixture(tmp_path, "one", "Example.Fixture")
    second = _fixture(tmp_path, "two", "example_fixture")
    with pytest.raises(ValueError, match="duplicate normalized fixture name") as error:
        discover_fixture_projects(tmp_path)
    assert str(first / "pyproject.toml") in str(error.value)
    assert str(second / "pyproject.toml") in str(error.value)


def test_new_fixture_automatically_enters_version_targets_and_set_coverage(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, "ninth", "ninth-fixture")
    paths = {target.path for target in targets("0.1.0", tmp_path)}
    expected = fixture.relative_to(tmp_path).as_posix() + "/pyproject.toml"
    assert expected in paths
    with pytest.raises(SystemExit, match="ninth-fixture"):
        validate_set_coverage(tmp_path, {"core-only": []})
    validate_set_coverage(tmp_path, {"fixture": ["ninth_fixture"]})


def test_build_helper_invokes_each_fixture_once_in_stable_order(
    tmp_path: Path,
) -> None:
    second = _fixture(tmp_path, "z-last", "z-fixture")
    first = _fixture(tmp_path, "a-first", "a-fixture")
    calls: list[tuple[list[str], Path]] = []

    def runner(command, *, cwd, check, text):
        assert check is True
        assert text is True
        calls.append((list(command), cwd))
        return subprocess.CompletedProcess(command, 0)

    output = tmp_path / "wheelhouse"
    fixtures = build_fixture_wheels(tmp_path, output, runner=runner)
    assert [item.path for item in fixtures] == [first.resolve(), second.resolve()]
    assert [call[0] for call in calls] == [
        ["uv", "build", str(first.resolve()), "--out-dir", str(output.resolve())],
        ["uv", "build", str(second.resolve()), "--out-dir", str(output.resolve())],
    ]
    assert all(cwd == tmp_path.resolve() for _, cwd in calls)


def test_build_helper_rejects_output_inside_fixture_source(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, "source")
    with pytest.raises(ValueError, match="aliases source"):
        build_fixture_wheels(tmp_path, fixture / "dist")


def test_build_helper_reports_first_failing_fixture(tmp_path: Path) -> None:
    _fixture(tmp_path, "a-first", "first-fixture")
    _fixture(tmp_path, "b-second", "second-fixture")
    calls = 0

    def runner(command, **_kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(RuntimeError, match=r"first-fixture.*a-first"):
        build_fixture_wheels(tmp_path, tmp_path / "wheelhouse", runner=runner)
    assert calls == 1
