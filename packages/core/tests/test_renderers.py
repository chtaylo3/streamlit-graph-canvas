import importlib.machinery
import os
import shutil
import subprocess
import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import streamlit_graph_canvas.renderers as renderer_module
from streamlit_graph_canvas import (
    RendererKind,
    RendererManifest,
    ValidationError,
    discover_renderer_manifests,
    enable_renderers,
    parse_renderer_manifest,
)


class FakeDistribution:
    def __init__(self, root: Path, manifest: str, name: str = "fake-renderer") -> None:
        package = root / "fake_renderer"
        package.mkdir(parents=True, exist_ok=True)
        (package / "renderer.toml").write_text(manifest, encoding="utf-8")
        self.files = [Path("fake_renderer/renderer.toml")]
        self.metadata = {"Name": name}
        self.version = "1.0.0"
        self.root = root

    def locate_file(self, file: Path) -> Path:
        return self.root / file

    def read_text(self, filename: str) -> str | None:
        return "fake_renderer\n" if filename == "top_level.txt" else None


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
    distributions = {
        name: FakeDistribution(tmp_path / name, manifest(distribution=name), name)
        for name in ("one", "two")
    }
    monkeypatch.setattr(
        renderer_module, "_renderer_distributions", lambda: distributions
    )
    monkeypatch.setattr(
        renderer_module,
        "parse_renderer_manifest",
        lambda dist: manifests[0] if dist.metadata["Name"] == "one" else manifests[1],
    )
    with pytest.raises(ValidationError) as error:
        enable_renderers(["one", "two"])
    assert error.value.diagnostic.code == "SGC_RENDERER_KIND_CONFLICT"


def test_unrequested_malformed_distribution_does_not_break_enablement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good = FakeDistribution(tmp_path / "good", manifest(distribution="good"), "good")
    bad = FakeDistribution(tmp_path / "bad", "not valid toml", "bad")
    declaration = RendererKind(
        "example/fixture/badge", None, None, frozenset({"atlas"})
    )
    valid_manifest = RendererManifest(
        "good", "1.0.0", 1, ">=1,<2", (declaration,), {}, tmp_path
    )
    parsed: list[str] = []

    def parse(dist: FakeDistribution) -> RendererManifest:
        parsed.append(dist.metadata["Name"])
        if dist is bad:
            raise AssertionError("unrequested manifest was parsed")
        return valid_manifest

    monkeypatch.setattr(
        renderer_module,
        "_renderer_distributions",
        lambda: {"bad": bad, "good": good},
    )
    monkeypatch.setattr(renderer_module, "parse_renderer_manifest", parse)

    registry = enable_renderers(["good"])

    assert parsed == ["good"]
    assert registry.require("example/fixture/badge", "atlas")


def test_contrib_renderer_is_loaded_only_after_enablement() -> None:
    manifests = discover_renderer_manifests()
    assert manifests[0].kinds
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    renderer = registry.require("streamlit-graph-canvas/contrib/count-chip", "prims")
    assert renderer.implementation is not None


def test_manifest_cache_detects_same_size_content_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = FakeDistribution(tmp_path, manifest(kind="example/fixture/alpha"))
    renderer_module._MANIFEST_CACHE.clear()

    first = renderer_module._cached_renderer_manifest(dist)  # type: ignore[arg-type]
    path = tmp_path / "fake_renderer" / "renderer.toml"
    before = path.stat()
    path.write_text(manifest(kind="example/fixture/bravo"), encoding="utf-8")
    assert path.stat().st_size == before.st_size
    os.utime(path, (before.st_atime, before.st_mtime))

    second = renderer_module._cached_renderer_manifest(dist)  # type: ignore[arg-type]

    assert first.kinds[0].kind == "example/fixture/alpha"
    assert second.kinds[0].kind == "example/fixture/bravo"
    assert first is not second


def test_manifest_cache_is_safe_under_concurrent_discovery(tmp_path: Path) -> None:
    dist = FakeDistribution(tmp_path, manifest())
    renderer_module._MANIFEST_CACHE.clear()

    with ThreadPoolExecutor(max_workers=8) as executor:
        manifests = list(
            executor.map(
                lambda _: renderer_module._cached_renderer_manifest(dist),  # type: ignore[arg-type]
                range(64),
            )
        )

    assert len({id(item) for item in manifests}) == 1


def test_module_ownership_requires_exact_distribution_file(tmp_path: Path) -> None:
    package = tmp_path / "shared_namespace"
    package.mkdir()
    owned = package / "owned.py"
    hostile = package / "hostile.py"
    owned.write_text("renderer = object()\n", encoding="utf-8")
    hostile.write_text("renderer = object()\n", encoding="utf-8")
    dist = FakeDistribution(tmp_path, manifest())
    dist.files.append(Path("shared_namespace/owned.py"))

    assert (
        renderer_module._distribution_module_origin(  # type: ignore[arg-type]
            dist, "shared_namespace.owned"
        )
        == owned.resolve()
    )
    assert (
        renderer_module._distribution_module_origin(  # type: ignore[arg-type]
            dist, "shared_namespace.hostile"
        )
        is None
    )


def test_module_ownership_accepts_a_record_owned_native_extension(
    tmp_path: Path,
) -> None:
    extension_root = Path(sysconfig.get_config_var("DESTSHARED"))
    origin = next(
        path
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
        for path in extension_root.glob(f"*{suffix}")
    )
    suffix = next(
        item
        for item in importlib.machinery.EXTENSION_SUFFIXES
        if origin.name.endswith(item)
    )
    package = tmp_path / "native_fixture"
    package.mkdir()
    extension = package / f"owned{suffix}"
    shutil.copyfile(origin, extension)
    dist = FakeDistribution(tmp_path, manifest())
    dist.files.append(Path("native_fixture") / extension.name)

    assert (
        renderer_module._distribution_module_origin(  # type: ignore[arg-type]
            dist, "native_fixture.owned"
        )
        == extension.resolve()
    )
    assert (
        renderer_module._distribution_module_origin(  # type: ignore[arg-type]
            dist, "native_fixture.unowned"
        )
        is None
    )
