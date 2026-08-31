import subprocess
import sys
from pathlib import Path

import pytest
import streamlit_graph_canvas.renderers as renderer_module
from streamlit_graph_canvas import (
    ValidationError,
    discover_renderer_manifests,
    enable_renderers,
)
from streamlit_graph_canvas.renderers import (
    RendererKind,
    RendererManifest,
    parse_renderer_manifest,
)


class FakeDistribution:
    def __init__(self, root: Path, manifest: str) -> None:
        package = root / "fake_renderer"
        package.mkdir(exist_ok=True)
        (package / "renderer.toml").write_text(manifest, encoding="utf-8")
        self.files = [Path("fake_renderer/renderer.toml")]
        self.metadata = {"Name": "fake-renderer"}
        self.version = "1.0.0"
        self.root = root

    def locate_file(self, file: Path) -> Path:
        return self.root / file

    def read_text(self, filename: str) -> None:
        return None


def manifest(**replacements: str) -> str:
    values = {
        "distribution": "fake-renderer",
        "version": "1.0.0",
        "api": ">=1,<2",
        "kind": "example/fixture/badge",
        **replacements,
    }
    return f'''manifest_schema = 1
distribution = "{values["distribution"]}"
version = "{values["version"]}"
renderer_api = "{values["api"]}"
[[renderers]]
kind = "{values["kind"]}"
python = "fake_renderer:renderer"
transports = ["prims"]
[assets]
'''


def test_discovery_does_not_import_renderer_packages() -> None:
    code = """
import sys
from streamlit_graph_canvas import discover_renderer_manifests
manifests = discover_renderer_manifests()
assert any(item.distribution == 'streamlit-graph-canvas-contrib' for item in manifests)
assert 'streamlit_graph_canvas_contrib' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"distribution": "wrong"}, "SGC_MANIFEST_DISTRIBUTION"),
        ({"version": "2.0"}, "SGC_MANIFEST_VERSION"),
        ({"api": ">=2"}, "SGC_RENDERER_API_INCOMPATIBLE"),
        ({"api": "not a range"}, "SGC_RENDERER_API_RANGE"),
        ({"kind": "not-namespaced"}, "SGC_RENDERER_KIND"),
        ({"version": "not a version"}, "SGC_MANIFEST_VERSION"),
    ],
)
def test_invalid_static_manifests_fail_closed(
    tmp_path: Path, change, code: str
) -> None:
    dist = FakeDistribution(tmp_path, manifest(**change))
    with pytest.raises(ValidationError) as error:
        parse_renderer_manifest(dist)  # type: ignore[arg-type]
    assert error.value.diagnostic.code == code


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (
            """manifest_schema = 1
distribution = "fake-renderer"
version = "1.0.0"
renderer_api = ">=1,<2"
renderers = "not-an-array"
""",
            "SGC_MANIFEST_RENDERERS",
        ),
        (
            manifest().replace("[[renderers]]", 'unexpected = "typo"\n[[renderers]]'),
            "SGC_MANIFEST_UNKNOWN",
        ),
        (
            manifest().replace('transports = ["prims"]', 'transports = "prims"'),
            "SGC_RENDERER_TRANSPORT",
        ),
        (
            manifest()
            + """[[renderers]]
kind = "example/fixture/badge"
python = "fake_renderer:renderer"
transports = ["prims"]
""",
            "SGC_RENDERER_DUPLICATE_KIND",
        ),
    ],
)
def test_malformed_manifest_shapes_are_diagnostics(
    tmp_path: Path, content: str, code: str
) -> None:
    with pytest.raises(ValidationError) as error:
        parse_renderer_manifest(FakeDistribution(tmp_path, content))  # type: ignore[arg-type]
    assert error.value.diagnostic.code == code


def test_manifest_asset_paths_and_hashes_are_verified(tmp_path: Path) -> None:
    digest = "0" * 64
    content = manifest() + f'"../outside.js" = "{digest}"\n'
    with pytest.raises(ValidationError) as error:
        parse_renderer_manifest(FakeDistribution(tmp_path, content))  # type: ignore[arg-type]
    assert error.value.diagnostic.code == "SGC_MANIFEST_ASSET_PATH"


def test_kind_conflicts_fail_before_any_renderer_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    kind = RendererKind(
        "example/fixture/badge",
        "module_that_must_not_import:renderer",
        None,
        frozenset({"prims"}),
    )
    manifests = tuple(
        RendererManifest(name, "1.0", 1, ">=1,<2", (kind,), {}, tmp_path)
        for name in ("one", "two")
    )
    monkeypatch.setattr(
        renderer_module, "discover_renderer_manifests", lambda: manifests
    )
    with pytest.raises(ValidationError) as error:
        enable_renderers(["one", "two"])
    assert error.value.diagnostic.code == "SGC_RENDERER_KIND_CONFLICT"


def test_contrib_renderer_is_loaded_only_after_enablement() -> None:
    manifests = discover_renderer_manifests()
    assert manifests[0].kinds
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    renderer = registry.require("streamlit-graph-canvas/contrib/count-chip", "prims")
    assert renderer.implementation is not None
