"""Fail closed when release wheels contain unexpected or unsafe files."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import zipfile
from email.parser import Parser
from pathlib import Path

FORBIDDEN_PARTS = {"node_modules", "__pycache__", ".env", ".git"}
FORBIDDEN_SUFFIXES = {".map", ".pem", ".key", ".pyc", ".pyo"}
MAX_WHEEL_BYTES = 25_000_000
MAX_UNCOMPRESSED_BYTES = 50_000_000
MAX_MEMBER_BYTES = 10_000_000


def inspect_wheel(path: Path) -> dict[str, object]:
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
        if any("frontend/src/" in name for name in names):
            raise SystemExit("core wheel contains frontend development sources")
    if path.name.startswith("streamlit_graph_canvas_contrib-"):
        if "streamlit_graph_canvas_contrib/renderer.toml" not in names:
            raise SystemExit("contrib wheel is missing renderer.toml")
        with zipfile.ZipFile(path) as archive:
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(archive.read(metadata_name).decode())
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
                if any(name.startswith("streamlit_graph_canvas._") for name in modules):
                    raise SystemExit(f"{source} imports a private core module")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheelhouse", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    verify_public_imports(args.root)
    wheels = sorted(args.wheelhouse.glob("streamlit_graph_canvas*.whl"))
    if len(wheels) < 2:
        raise SystemExit("expected built core and contrib wheels")
    print(
        json.dumps([inspect_wheel(path) for path in wheels], indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
