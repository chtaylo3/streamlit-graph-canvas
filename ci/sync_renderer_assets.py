"""Synchronize immutable JavaScript renderer identities and content-addressed names."""

from __future__ import annotations

import argparse
import hashlib
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).parents[1]
IDENTITY = re.compile(r'const buildIdentity = "([0-9a-f]{64})";')
CONTENT_NAME = re.compile(r"^(?P<base>.+?)(?:\.[0-9a-f]{64})?\.js$")


def _renderer_manifests(root: Path) -> tuple[Path, ...]:
    locations = (
        root / "packages/contrib/src",
        root / "tests/e2e/fixtures",
    )
    return tuple(
        sorted(
            path for location in locations for path in location.rglob("renderer.toml")
        )
    )


def discover_renderer_javascript_assets(root: Path = ROOT) -> tuple[Path, ...]:
    """Return validated JavaScript assets from parseable renderer manifests."""

    discovered: list[Path] = []
    seen: dict[Path, Path] = {}
    for manifest in _renderer_manifests(root.resolve()):
        try:
            raw: dict[str, Any] = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            continue
        renderers = raw.get("renderers", [])
        if not isinstance(renderers, list):
            raise ValueError(f"{manifest}: renderers must be an array of tables")
        manifest_root = manifest.parent.resolve()
        for renderer in renderers:
            if not isinstance(renderer, dict) or "javascript" not in renderer:
                continue
            relative = renderer["javascript"]
            if not isinstance(relative, str) or not relative or "\\" in relative:
                raise ValueError(
                    f"{manifest}: invalid JavaScript asset path {relative!r}"
                )
            posix = PurePosixPath(relative)
            if posix.is_absolute() or ".." in posix.parts:
                raise ValueError(
                    f"{manifest}: JavaScript asset escapes manifest: {relative}"
                )
            asset = manifest_root.joinpath(*posix.parts).resolve()
            if not asset.is_relative_to(manifest_root):
                raise ValueError(
                    f"{manifest}: JavaScript asset escapes manifest: {relative}"
                )
            if not asset.is_file():
                raise ValueError(f"{manifest}: JavaScript asset is missing: {relative}")
            previous = seen.get(asset)
            if previous is not None:
                raise ValueError(
                    f"duplicate JavaScript asset declaration {asset}: "
                    f"{previous} and {manifest}"
                )
            seen[asset] = manifest
            discovered.append(asset)
    return tuple(sorted(discovered))


def _replace_exact(text: str, old: str, new: str, *, subject: Path) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{subject}: expected exactly one {old!r}")
    return text.replace(old, new)


def _sync_manifest(path: Path, *, write: bool) -> list[str]:
    manifest_text = path.read_text(encoding="utf-8")
    try:
        raw: dict[str, Any] = tomllib.loads(manifest_text)
    except tomllib.TOMLDecodeError:
        return []
    stale: list[str] = []
    for renderer in raw.get("renderers", []):
        relative = renderer.get("javascript")
        if not isinstance(relative, str):
            continue
        asset = path.parent / relative
        if not asset.is_file():
            raise ValueError(f"{path}: JavaScript asset is missing: {relative}")
        source = asset.read_text(encoding="utf-8")
        match = IDENTITY.search(source)
        if match is None:
            raise ValueError(f"{asset}: generated buildIdentity constant is missing")
        normalized = source[: match.start(1)] + "0" * 64 + source[match.end(1) :]
        identity = hashlib.sha256(normalized.encode()).hexdigest()
        synchronized = source[: match.start(1)] + identity + source[match.end(1) :]
        digest = hashlib.sha256(synchronized.encode()).hexdigest()
        name_match = CONTENT_NAME.fullmatch(asset.name)
        if name_match is None:
            raise ValueError(f"{asset}: JavaScript asset name is unsupported")
        desired_name = f"{name_match.group('base')}.{digest}.js"
        desired_relative = str(Path(relative).with_name(desired_name)).replace(
            "\\", "/"
        )
        expected_hash = raw.get("assets", {}).get(relative)
        declared_identity = renderer.get("javascript_identity")
        entry = renderer.get("javascript_entry")
        is_stale = (
            source != synchronized
            or asset.name != desired_name
            or expected_hash != digest
            or declared_identity != identity
            or entry != desired_name
        )
        if not is_stale:
            continue
        stale.append(str(asset))
        if not write:
            continue
        updated = manifest_text
        updated = _replace_exact(
            updated,
            f'javascript = "{relative}"',
            f'javascript = "{desired_relative}"',
            subject=path,
        )
        updated = _replace_exact(
            updated,
            f'javascript_entry = "{entry}"',
            f'javascript_entry = "{desired_name}"',
            subject=path,
        )
        updated = _replace_exact(
            updated,
            f'javascript_identity = "{declared_identity}"',
            f'javascript_identity = "{identity}"',
            subject=path,
        )
        updated = _replace_exact(
            updated,
            f'"{relative}" = "{expected_hash}"',
            f'"{desired_relative}" = "{digest}"',
            subject=path,
        )
        destination = asset.with_name(desired_name)
        if destination != asset and destination.exists():
            raise ValueError(f"{destination}: refusing to replace existing asset")
        asset.write_text(synchronized, encoding="utf-8")
        if destination != asset:
            asset.replace(destination)
        path.write_text(updated, encoding="utf-8")
        manifest_text = updated
        raw = tomllib.loads(updated)
    return stale


def synchronize(root: Path = ROOT, *, write: bool) -> list[str]:
    stale: list[str] = []
    for manifest in _renderer_manifests(root):
        stale.extend(_sync_manifest(manifest, write=write))
    return stale


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    stale = synchronize(args.root, write=not args.check)
    if args.check and stale:
        raise SystemExit("renderer assets are stale: " + ", ".join(stale))
    print("renderer assets are synchronized")


if __name__ == "__main__":
    main()
