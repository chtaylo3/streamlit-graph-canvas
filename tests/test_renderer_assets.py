from pathlib import Path

from ci.sync_renderer_assets import synchronize


def _fixture(root: Path) -> tuple[Path, Path]:
    package = root / "packages" / "contrib" / "src" / "fixture"
    frontend = package / "frontend"
    frontend.mkdir(parents=True)
    asset = frontend / "bootstrap.js"
    asset.write_text(
        'const buildIdentity = "' + "0" * 64 + '";\nexport default () => {};\n',
        encoding="utf-8",
    )
    manifest = package / "renderer.toml"
    manifest.write_text(
        '''manifest_schema = 1
distribution = "fixture"
version = "1.0.0"
renderer_api = ">=1,<2"

[[renderers]]
kind = "vendor/fixture/example"
javascript = "frontend/bootstrap.js"
javascript_component = "fixture.bootstrap"
javascript_entry = "bootstrap.js"
javascript_identity = "'''
        + "0" * 64
        + '''"
transports = ["javascript"]

[assets]
"frontend/bootstrap.js" = "'''
        + "0" * 64
        + """"
""",
        encoding="utf-8",
    )
    return manifest, asset


def test_renderer_asset_sync_detects_and_repairs_stale_assets(tmp_path: Path) -> None:
    manifest, old_asset = _fixture(tmp_path)

    assert synchronize(tmp_path, write=False)
    assert old_asset.is_file()

    assert synchronize(tmp_path, write=True)
    assert synchronize(tmp_path, write=False) == []
    assert not old_asset.exists()
    updated = manifest.read_text(encoding="utf-8")
    assert 'javascript = "frontend/bootstrap.' in updated
    assert 'javascript_identity = "' + "0" * 64 + '"' not in updated


def test_renderer_asset_sync_detects_post_generation_mutation(tmp_path: Path) -> None:
    _, _ = _fixture(tmp_path)
    synchronize(tmp_path, write=True)
    generated = next(tmp_path.rglob("bootstrap.*.js"))
    generated.write_text(
        generated.read_text(encoding="utf-8") + "// tampered\n",
        encoding="utf-8",
    )

    assert synchronize(tmp_path, write=False)
