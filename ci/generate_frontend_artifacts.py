"""Build frontend artifacts in staging and compare or materialize them."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .generate_frontend_licenses import generate
else:
    from generate_frontend_licenses import generate

BUILD_RELATIVE = Path("packages/core/src/streamlit_graph_canvas/frontend/build")
LICENSE_RELATIVE = Path("packages/core/THIRD_PARTY_LICENSES.md")


def artifact_differences(
    expected: dict[Path, bytes], actual: dict[Path, bytes]
) -> dict[str, list[str]]:
    expected_names = set(expected)
    actual_names = set(actual)
    return {
        "missing": sorted(str(path) for path in expected_names - actual_names),
        "obsolete": sorted(str(path) for path in actual_names - expected_names),
        "changed": sorted(
            str(path)
            for path in expected_names & actual_names
            if expected[path] != actual[path]
        ),
    }


def _files(root: Path) -> dict[Path, bytes]:
    build = root / BUILD_RELATIVE
    files = {
        path.relative_to(root): path.read_bytes()
        for path in build.rglob("*")
        if path.is_file()
    }
    license_path = root / LICENSE_RELATIVE
    if license_path.is_file():
        files[LICENSE_RELATIVE] = license_path.read_bytes()
    return files


def _stage(root: Path, staging: Path) -> dict[Path, bytes]:
    source = root / BUILD_RELATIVE.parent
    frontend = staging / BUILD_RELATIVE.parent
    frontend.parent.mkdir(parents=True)
    shutil.copytree(
        source,
        frontend,
        ignore=shutil.ignore_patterns("node_modules", "build"),
    )
    subprocess.run(["npm", "ci"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)
    document, machine = generate(root, frontend=frontend)
    (frontend / "build/third-party-licenses.json").write_bytes(machine)
    license_path = staging / LICENSE_RELATIVE
    license_path.parent.mkdir(parents=True, exist_ok=True)
    license_path.write_bytes(document)
    return _files(staging)


def synchronize(root: Path, *, write: bool) -> dict[str, list[str]]:
    with tempfile.TemporaryDirectory(prefix="sgc-frontend-artifacts-") as temporary:
        expected = _stage(root, Path(temporary))
        actual = _files(root)
        differences = artifact_differences(expected, actual)
        if write:
            build = root / BUILD_RELATIVE
            if build.exists():
                shutil.rmtree(build)
            build.mkdir(parents=True)
            for relative, content in expected.items():
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            differences = artifact_differences(expected, _files(root))
        return differences


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    differences = synchronize(args.root.resolve(), write=args.write)
    if any(differences.values()):
        raise SystemExit(f"frontend artifacts are stale: {differences}")
    print("frontend artifacts are synchronized")


if __name__ == "__main__":
    main()
