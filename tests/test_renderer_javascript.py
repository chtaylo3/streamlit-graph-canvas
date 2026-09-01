from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from ci.check_renderer_javascript import (
    NODE_ESM_CHECK,
    check_renderer_javascript,
    verify_module_parser,
)
from ci.sync_renderer_assets import discover_renderer_javascript_assets

ROOT = Path(__file__).parents[1]


def _manifest(root: Path, javascript_lines: str) -> Path:
    package = root / "packages/contrib/src/fixture"
    package.mkdir(parents=True)
    manifest = package / "renderer.toml"
    manifest.write_text(
        "manifest_schema = 1\n"
        'distribution = "fixture"\n'
        'version = "0.1.0"\n'
        'renderer_api = ">=1,<2"\n'
        f"{javascript_lines}",
        encoding="utf-8",
    )
    return manifest


def _successful_runner(calls: list[tuple[str, ...]]):
    def runner(command, *, input, capture_output, text, check):
        calls.append(tuple(command))
        assert capture_output is True and text is True and check is False
        return subprocess.CompletedProcess(
            command,
            1 if input == "export const = ;\n" else 0,
            stdout="",
            stderr="expected syntax error" if input == "export const = ;\n" else "",
        )

    return runner


def test_repository_discovers_stock_and_five_fixture_bootstraps() -> None:
    assets = discover_renderer_javascript_assets(ROOT)
    assert len(assets) == 6
    assert any(
        "streamlit_graph_canvas_contrib/frontend" in path.as_posix() for path in assets
    )
    assert sum("tests/e2e/fixtures" in path.as_posix() for path in assets) == 5


@pytest.mark.parametrize(
    ("relative", "message"),
    (
        ("frontend/missing.js", "missing"),
        ("../escaping.js", "escapes"),
        ("/absolute.js", "escapes"),
    ),
)
def test_asset_discovery_rejects_missing_or_escaping_paths(
    tmp_path: Path, relative: str, message: str
) -> None:
    _manifest(
        tmp_path,
        "[[renderers]]\n"
        'kind = "example/fixture/badge"\n'
        f'javascript = "{relative}"\n'
        'transports = ["javascript"]\n',
    )
    with pytest.raises(ValueError, match=message):
        discover_renderer_javascript_assets(tmp_path)


def test_asset_discovery_rejects_duplicate_declarations(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        "[[renderers]]\n"
        'kind = "example/fixture/one"\n'
        'javascript = "frontend/bootstrap.js"\n'
        'transports = ["javascript"]\n'
        "[[renderers]]\n"
        'kind = "example/fixture/two"\n'
        'javascript = "frontend/bootstrap.js"\n'
        'transports = ["javascript"]\n',
    )
    asset = manifest.parent / "frontend/bootstrap.js"
    asset.parent.mkdir()
    asset.write_text("export {};\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JavaScript asset"):
        discover_renderer_javascript_assets(tmp_path)


def test_asset_discovery_skips_deliberately_malformed_toml(tmp_path: Path) -> None:
    package = tmp_path / "tests/e2e/fixtures/malformed/src/package"
    package.mkdir(parents=True)
    (package / "renderer.toml").write_text("not = [ valid", encoding="utf-8")
    assert discover_renderer_javascript_assets(tmp_path) == ()


def test_node_parser_uses_exact_module_aware_argument_vector() -> None:
    calls: list[tuple[str, ...]] = []
    verify_module_parser(runner=_successful_runner(calls))
    assert calls == [NODE_ESM_CHECK, NODE_ESM_CHECK]


def test_checker_reports_invalid_asset_path_and_preserves_bytes(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        "[[renderers]]\n"
        'kind = "example/fixture/badge"\n'
        'javascript = "frontend/bootstrap.js"\n'
        'transports = ["javascript"]\n',
    )
    asset = manifest.parent / "frontend/bootstrap.js"
    asset.parent.mkdir()
    asset.write_text("export const broken = ;\n", encoding="utf-8")
    before = hashlib.sha256(asset.read_bytes()).hexdigest()

    def runner(command, *, input, capture_output, text, check):
        if input == "export const = ;\n":
            return subprocess.CompletedProcess(command, 1, "", "probe rejected")
        if "broken" in input:
            return subprocess.CompletedProcess(command, 1, "", "Unexpected token")
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises(RuntimeError, match=r"bootstrap\.js: Unexpected token"):
        check_renderer_javascript(tmp_path, runner=runner)
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == before


def test_repository_checker_is_read_only_with_injected_module_parser() -> None:
    assets = discover_renderer_javascript_assets(ROOT)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in assets}
    calls: list[tuple[str, ...]] = []
    assert check_renderer_javascript(ROOT, runner=_successful_runner(calls)) == assets
    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in assets
    } == before
    assert all(call == NODE_ESM_CHECK for call in calls)
