"""Safely inspect sdists, rebuild offline, compare wheels, and emit evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

MAX_SDIST_BYTES = 30_000_000
MAX_SDIST_MEMBERS = 2_000
MAX_SDIST_MEMBER_BYTES = 10_000_000
MAX_SDIST_EXPANDED_BYTES = 60_000_000


def safe_extract_sdist(archive_path: Path, destination: Path) -> Path:
    if archive_path.stat().st_size > MAX_SDIST_BYTES:
        raise ValueError("sdist exceeds compressed size limit")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > MAX_SDIST_MEMBERS:
            raise ValueError("sdist has too many members")
        names: set[str] = set()
        folded: set[str] = set()
        total = 0
        roots: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or not path.parts
                or any(part in {"", ".", ".."} for part in path.parts)
                or "\\" in member.name
            ):
                raise ValueError(f"unsafe sdist path: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported sdist member type: {member.name!r}")
            if member.size > MAX_SDIST_MEMBER_BYTES:
                raise ValueError(f"oversized sdist member: {member.name!r}")
            total += member.size
            if total > MAX_SDIST_EXPANDED_BYTES:
                raise ValueError("sdist exceeds expanded size limit")
            normalized = str(path)
            if normalized in names or normalized.casefold() in folded:
                raise ValueError(f"duplicate sdist path: {member.name!r}")
            names.add(normalized)
            folded.add(normalized.casefold())
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("sdist must contain exactly one top-level directory")
        destination.mkdir(parents=True, exist_ok=False)
        resolved_destination = destination.resolve()
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if not target.resolve().is_relative_to(resolved_destination):
                raise ValueError(f"sdist path escapes destination: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"sdist member cannot be read: {member.name!r}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
    return destination / next(iter(roots))


def normalized_wheel(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith(".dist-info/RECORD")
        }


def compare_wheels(direct: Path, rebuilt: Path) -> None:
    left = normalized_wheel(direct)
    right = normalized_wheel(rebuilt)
    if left.keys() != right.keys():
        missing = sorted(left.keys() - right.keys())
        extra = sorted(right.keys() - left.keys())
        raise ValueError(
            f"rebuilt wheel members differ: missing={missing}, extra={extra}"
        )
    changed = sorted(name for name in left if left[name] != right[name])
    if changed:
        raise ValueError(f"rebuilt wheel contents differ: {changed}")


def _distribution_prefix(path: Path) -> str:
    return path.name.split("-", 1)[0].replace("-", "_").casefold()


def _single(directory: Path, prefix: str, suffix: str) -> Path:
    matches = [
        path
        for path in directory.iterdir()
        if _distribution_prefix(path) == prefix and path.name.endswith(suffix)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {prefix} {suffix} artifact, found {matches}")
    return matches[0]


def _sbom(wheel: Path) -> bytes:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        components = []
        for requirement in metadata.get_all("Requires-Dist", []):
            name = re.split(r"[ <>=!~;\[]", requirement, maxsplit=1)[0]
            components.append({"type": "library", "name": name})
        bundle = next(
            (
                name
                for name in archive.namelist()
                if name.endswith("frontend/build/bundled-packages.json")
            ),
            None,
        )
        if bundle:
            for item in json.loads(archive.read(bundle))["packages"]:
                components.append(
                    {
                        "type": "library",
                        "name": item["name"],
                        "version": item["version"],
                        "properties": [
                            {"name": "sgc:surface", "value": "bundled-frontend"}
                        ],
                    }
                )
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "name": metadata["Name"],
                "version": metadata["Version"],
                "hashes": [
                    {
                        "alg": "SHA-256",
                        "content": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                    }
                ],
            }
        },
        "components": sorted(
            components,
            key=lambda item: (item["name"].casefold(), item.get("version", "")),
        ),
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def verify(
    direct: Path, output: Path, build_wheelhouse: Path, build_requirement: str
) -> None:
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="sgc-sdist-rebuild-") as temporary:
        temporary_root = Path(temporary)
        venv = temporary_root / "build-venv"
        subprocess.run(["uv", "venv", str(venv)], check=True)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--offline",
                "--no-index",
                "--find-links",
                str(build_wheelhouse.resolve()),
                build_requirement,
            ],
            check=True,
        )
        for prefix in ("streamlit_graph_canvas", "streamlit_graph_canvas_contrib"):
            sdist = _single(direct, prefix, ".tar.gz")
            direct_wheel = _single(direct, prefix, ".whl")
            source = safe_extract_sdist(sdist, temporary_root / f"source-{prefix}")
            rebuilt_dir = temporary_root / f"rebuilt-{prefix}"
            rebuilt_dir.mkdir()
            subprocess.run(
                [
                    "uv",
                    "build",
                    "--wheel",
                    "--offline",
                    "--no-build-isolation",
                    "--python",
                    str(python),
                    "--out-dir",
                    str(rebuilt_dir),
                    str(source),
                ],
                check=True,
            )
            rebuilt = next(rebuilt_dir.glob("*.whl"))
            compare_wheels(direct_wheel, rebuilt)
            copied_wheel = output / rebuilt.name
            copied_sdist = output / sdist.name
            shutil.copy2(rebuilt, copied_wheel)
            shutil.copy2(sdist, copied_sdist)
            (output / f"{prefix}.cdx.json").write_bytes(_sbom(copied_wheel))
    evidence = sorted(path for path in output.iterdir() if path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in evidence
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("direct", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--build-wheelhouse", type=Path, required=True)
    parser.add_argument("--build-requirement", required=True)
    args = parser.parse_args()
    verify(
        args.direct,
        args.output,
        args.build_wheelhouse,
        args.build_requirement,
    )


if __name__ == "__main__":
    main()
