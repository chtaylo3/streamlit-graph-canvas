"""Generate and verify frontend third-party licensing artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

LICENSE_NAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "LICENCE",
    "LICENCE.md",
    "COPYING",
)

# npm's 1.0.0 tarball omits LICENSE. Its src/index.ts exactly matches this
# npm gitHead and explicitly refers to the repository-root MIT license.
COMPILER_RUNTIME_SOURCE = (
    "https://raw.githubusercontent.com/facebook/react/"
    "5c15c1cd3442f28044217703b5625f98c40042ee/LICENSE"
)
COMPILER_RUNTIME_INTEGRITY = (
    "sha512-rRfjYv66HlG8896yPUDONgKzG5BxZD1nV9U6rkm+7VCuvQc903C4MjcoZR4zPw53I"
    "KSOX9wMQVpA1IAbRtzQ7w=="
)
COMPILER_RUNTIME_LICENSE_SHA256 = (
    "da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93"
)


def _bundled_packages(
    lock: dict[str, Any], bundle: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    if bundle.get("schema") != 1 or not isinstance(bundle.get("packages"), list):
        raise SystemExit("Bundled-package inventory has an unsupported shape")
    locked: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for package_path, metadata in lock["packages"].items():
        if not package_path.startswith("node_modules/"):
            continue
        name = package_path.rsplit("node_modules/", 1)[-1]
        locked[(name, str(metadata["version"]))] = (name, metadata)
    selected: list[tuple[str, dict[str, Any]]] = []
    for item in bundle["packages"]:
        if not isinstance(item, dict) or set(item) != {"name", "version"}:
            raise SystemExit("Bundled-package inventory contains a malformed entry")
        identity = (item["name"], item["version"])
        if identity not in locked:
            raise SystemExit(
                f"Bundled dependency is absent from package-lock.json: {identity}"
            )
        selected.append(locked[identity])
    return sorted(selected, key=lambda item: item[0].casefold())


def _license_file(
    package_dir: Path,
    *,
    root: Path,
    package: dict[str, Any],
    locked: dict[str, Any],
) -> tuple[Path, str | None]:
    for name in LICENSE_NAMES:
        candidate = package_dir / name
        if candidate.is_file():
            return candidate, None
    if (
        package.get("name") == "react-compiler-runtime"
        and package.get("version") == locked.get("version") == "1.0.0"
        and package.get("license") == "MIT"
        and locked.get("integrity") == COMPILER_RUNTIME_INTEGRITY
        and locked.get("resolved")
        == "https://registry.npmjs.org/react-compiler-runtime/-/"
        "react-compiler-runtime-1.0.0.tgz"
    ):
        reviewed = root / "ci/frontend-licenses/react-compiler-runtime-1.0.0.LICENSE"
        if not reviewed.is_file() or (
            hashlib.sha256(reviewed.read_bytes()).hexdigest()
            != COMPILER_RUNTIME_LICENSE_SHA256
        ):
            raise SystemExit(
                "Reviewed react-compiler-runtime license is missing or changed"
            )
        return reviewed, COMPILER_RUNTIME_SOURCE
    raise SystemExit(f"No license text found for {package_dir.name!r}")


def generate(root: Path, *, frontend: Path | None = None) -> tuple[bytes, bytes]:
    frontend = frontend or (root / "packages/core/src/streamlit_graph_canvas/frontend")
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    bundle = json.loads(
        (frontend / "build/bundled-packages.json").read_text(encoding="utf-8")
    )
    inventory: list[dict[str, str]] = []
    sections: list[str] = [
        "# Frontend third-party licenses",
        "",
        "This file is generated from the modules in the production bundle, reconciled",
        "to the locked dependency graph, by",
        "`ci/generate_frontend_licenses.py`. Do not edit it manually.",
        "",
        "The project selects the EPL-2.0 option for elkjs. Bundled dependencies are",
        "redistributed without source modifications by this project.",
    ]
    for name, metadata in _bundled_packages(lock, bundle):
        package_dir = frontend / "node_modules" / name
        package_json = json.loads(
            (package_dir / "package.json").read_text(encoding="utf-8")
        )
        license_path, license_source = _license_file(
            package_dir, root=root, package=package_json, locked=metadata
        )
        license_text = license_path.read_text(encoding="utf-8").strip()
        declared = str(package_json.get("license") or metadata.get("license") or "")
        if not declared:
            raise SystemExit(f"No declared license found for {name!r}")
        selected = "EPL-2.0" if name == "elkjs" else declared
        digest = hashlib.sha256(license_text.encode()).hexdigest()
        inventory.append(
            {
                "name": name,
                "version": str(metadata["version"]),
                "declared_license": declared,
                "selected_license": selected,
                "license_file": license_path.name,
                "license_sha256": digest,
            }
        )
        if license_source:
            inventory[-1]["license_source"] = license_source
        sections.extend(
            [
                "",
                f"## {name} {metadata['version']}",
                "",
                f"Declared license: `{declared}`",
                "",
                *([f"License source: {license_source}", ""] if license_source else []),
                "```text",
                license_text,
                "```",
            ]
        )
    document = ("\n".join(sections) + "\n").encode()
    machine = (
        json.dumps(
            {
                "schema": 1,
                "source": ["build/bundled-packages.json", "package-lock.json"],
                "packages": inventory,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    return document, machine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document, machine = generate(args.root)
    outputs = {
        args.root / "packages/core/THIRD_PARTY_LICENSES.md": document,
        args.root
        / (
            "packages/core/src/streamlit_graph_canvas/frontend/build/"
            "third-party-licenses.json"
        ): machine,
    }
    if args.check:
        stale = [
            path
            for path, content in outputs.items()
            if not path.is_file() or path.read_bytes() != content
        ]
        if stale:
            raise SystemExit(f"Frontend licensing artifacts are stale: {stale}")
        return
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    main()
