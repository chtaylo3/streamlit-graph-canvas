"""Fail closed when release wheels contain unexpected or unsafe files."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

from .sync_versions import synchronize

FORBIDDEN_PARTS = {"node_modules", "__pycache__", ".env", ".git"}
FORBIDDEN_SUFFIXES = {".map", ".pem", ".key", ".pyc", ".pyo"}
MAX_WHEEL_BYTES = 25_000_000
MAX_UNCOMPRESSED_BYTES = 50_000_000
MAX_MEMBER_BYTES = 10_000_000


def inspect_wheel(path: Path, root: Path) -> dict[str, object]:
    if path.stat().st_size > MAX_WHEEL_BYTES:
        raise SystemExit(f"{path.name} exceeds the compressed wheel size limit")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
    names = [member.filename for member in members]
    unsafe_names = [
        name
        for name in names
        if Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name
    ]
    if unsafe_names:
        raise SystemExit(f"{path.name} contains unsafe archive paths: {unsafe_names}")
    if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_BYTES:
        raise SystemExit(f"{path.name} exceeds the uncompressed wheel size limit")
    oversized = [
        member.filename for member in members if member.file_size > MAX_MEMBER_BYTES
    ]
    if oversized:
        raise SystemExit(f"{path.name} contains oversized files: {oversized}")
    violations = [
        name
        for name in names
        if FORBIDDEN_PARTS.intersection(Path(name).parts)
        or Path(name).suffix.lower() in FORBIDDEN_SUFFIXES
    ]
    if violations:
        raise SystemExit(f"{path.name} contains forbidden files: {violations}")
    if not any("dist-info/licenses/LICENSE" in name for name in names):
        raise SystemExit(f"{path.name} does not package its license")
    if path.name.startswith("streamlit_graph_canvas-"):
        required = {
            "streamlit_graph_canvas/py.typed",
            "streamlit_graph_canvas/pyproject.toml",
        }
        if not required <= set(names):
            raise SystemExit(
                f"core wheel is missing component metadata: {required - set(names)}"
            )
        if not any(
            name.startswith("streamlit_graph_canvas/frontend/build/index-")
            and name.endswith(".js")
            for name in names
        ):
            raise SystemExit("core wheel is missing its compiled JavaScript asset")
        javascript = [
            name
            for name in names
            if name.startswith("streamlit_graph_canvas/frontend/build/index-")
            and name.endswith(".js")
        ]
        stylesheets = [
            name
            for name in names
            if name.startswith("streamlit_graph_canvas/frontend/build/index-")
            and name.endswith(".css")
        ]
        if len(javascript) != 1 or len(stylesheets) != 1:
            raise SystemExit("core wheel must contain exactly one JS and CSS bundle")
        if any("_hash_" in name for name in stylesheets):
            raise SystemExit("core wheel CSS is not content-addressed")
        inventory_name = (
            "streamlit_graph_canvas/frontend/build/third-party-licenses.json"
        )
        bundle_inventory_name = (
            "streamlit_graph_canvas/frontend/build/bundled-packages.json"
        )
        if {inventory_name, bundle_inventory_name} - set(names):
            raise SystemExit("core wheel is missing a frontend license inventory")
        if not any("dist-info/licenses/NOTICE" in name for name in names):
            raise SystemExit("core wheel does not package NOTICE")
        if not any(
            "dist-info/licenses/THIRD_PARTY_LICENSES.md" in name for name in names
        ):
            raise SystemExit("core wheel does not package third-party license texts")
        with zipfile.ZipFile(path) as archive:
            inventory_bytes = archive.read(inventory_name)
            inventory = json.loads(inventory_bytes)
            bundle_inventory = json.loads(archive.read(bundle_inventory_name))
        expected_inventory = root / (
            "packages/core/src/streamlit_graph_canvas/frontend/build/"
            "third-party-licenses.json"
        )
        if (
            not expected_inventory.is_file()
            or inventory_bytes != expected_inventory.read_bytes()
        ):
            raise SystemExit("core wheel license inventory is stale")
        packages = inventory.get("packages", [])
        if not packages or any(
            not all(
                item.get(field)
                for field in (
                    "name",
                    "version",
                    "declared_license",
                    "selected_license",
                    "license_sha256",
                )
            )
            for item in packages
        ):
            raise SystemExit("core wheel has an incomplete license inventory")
        licensed = {(item["name"], item["version"]) for item in packages}
        bundled = {
            (item["name"], item["version"])
            for item in bundle_inventory.get("packages", [])
        }
        if not bundled or bundled != licensed:
            raise SystemExit(
                "core wheel bundled-code and license inventories do not match"
            )
        elk = [item for item in packages if item["name"] == "elkjs"]
        if len(elk) != 1 or elk[0]["selected_license"] != "EPL-2.0":
            raise SystemExit("core wheel must record the selected elkjs license")
        if any("frontend/src/" in name for name in names):
            raise SystemExit("core wheel contains frontend development sources")
    if path.name.startswith("streamlit_graph_canvas_contrib-"):
        required = {
            "streamlit_graph_canvas_contrib/py.typed",
            "streamlit_graph_canvas_contrib/renderer.toml",
        }
        if not required <= set(names):
            raise SystemExit(
                f"contrib wheel is missing required files: {required - set(names)}"
            )
        with zipfile.ZipFile(path) as archive:
            renderer_manifest = tomllib.loads(
                archive.read("streamlit_graph_canvas_contrib/renderer.toml").decode()
            )
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(archive.read(metadata_name).decode())
            for asset, expected_hash in renderer_manifest.get("assets", {}).items():
                packaged_asset = f"streamlit_graph_canvas_contrib/{asset}"
                if packaged_asset not in names:
                    raise SystemExit(f"contrib wheel is missing {packaged_asset}")
                if (
                    hashlib.sha256(archive.read(packaged_asset)).hexdigest()
                    != expected_hash
                ):
                    raise SystemExit(f"contrib asset hash mismatch: {packaged_asset}")
                if asset.endswith(".js") and not Path(asset).name.endswith(
                    f".{expected_hash}.js"
                ):
                    raise SystemExit(
                        f"contrib asset is not content-addressed: {packaged_asset}"
                    )
            javascript_renderers = [
                renderer
                for renderer in renderer_manifest["renderers"]
                if "javascript" in renderer["transports"]
            ]
            if javascript_renderers and (
                "streamlit_graph_canvas_contrib/pyproject.toml" not in names
                or any(
                    not all(
                        renderer.get(field)
                        for field in (
                            "javascript",
                            "javascript_component",
                            "javascript_entry",
                        )
                    )
                    for renderer in javascript_renderers
                )
            ):
                raise SystemExit(
                    "contrib JavaScript renderer is missing component metadata"
                )
            for renderer in javascript_renderers:
                asset = renderer["javascript"]
                source = archive.read(
                    f"streamlit_graph_canvas_contrib/{asset}"
                ).decode()
                identity = renderer.get("javascript_identity")
                if source.count(f'const buildIdentity = "{identity}";') != 1:
                    raise SystemExit(
                        "contrib JavaScript embedded identity does not match manifest"
                    )
        requirement = next(
            (
                item
                for item in metadata.get_all("Requires-Dist", ())
                if item.startswith("streamlit-graph-canvas")
            ),
            "",
        )
        if not re.search(r"<\s*0\.2", requirement):
            raise SystemExit("contrib must bound its compatible pre-1.0 core range")
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "files": len(names),
        "bytes": path.stat().st_size,
    }


def verify_public_imports(root: Path) -> None:
    public_module = root / "packages/core/src/streamlit_graph_canvas/__init__.py"
    tree = ast.parse(public_module.read_text(encoding="utf-8"))
    public: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            public = {
                item.value for item in node.value.elts if isinstance(item, ast.Constant)
            }
    for source in (root / "packages/contrib/src").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "streamlit_graph_canvas"
            ):
                private = sorted(
                    alias.name for alias in node.names if alias.name not in public
                )
                if private:
                    raise SystemExit(
                        f"{source} imports non-public core names: {private}"
                    )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                if any(name.startswith("streamlit_graph_canvas.") for name in modules):
                    raise SystemExit(f"{source} bypasses the root-only public core API")


def verify_versions(root: Path) -> None:
    stale = synchronize(root, write=False)
    if stale:
        raise SystemExit(f"derived project versions are inconsistent: {stale}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheelhouse", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    verify_public_imports(args.root)
    verify_versions(args.root)
    wheels = sorted(args.wheelhouse.glob("streamlit_graph_canvas*.whl"))
    if len(wheels) < 2:
        raise SystemExit("expected built core and contrib wheels")
    print(
        json.dumps(
            [inspect_wheel(path, args.root) for path in wheels],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
