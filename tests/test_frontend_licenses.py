from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ci.generate_frontend_licenses import (
    COMPILER_RUNTIME_INTEGRITY,
    COMPILER_RUNTIME_SOURCE,
    generate,
)

ROOT = Path(__file__).parents[1]
REVIEWED = Path("ci/frontend-licenses/react-compiler-runtime-1.0.0.LICENSE")


@pytest.fixture
def frontend(tmp_path: Path) -> Path:
    directory = tmp_path / "frontend"
    package = directory / "node_modules/react-compiler-runtime"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps(
            {"name": "react-compiler-runtime", "version": "1.0.0", "license": "MIT"}
        )
    )
    (directory / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/react-compiler-runtime": {
                        "version": "1.0.0",
                        "integrity": COMPILER_RUNTIME_INTEGRITY,
                        "resolved": "https://registry.npmjs.org/react-compiler-runtime/-/react-compiler-runtime-1.0.0.tgz",
                    }
                }
            }
        )
    )
    (directory / "build").mkdir()
    (directory / "build/bundled-packages.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "packages": [{"name": "react-compiler-runtime", "version": "1.0.0"}],
            }
        )
    )
    (tmp_path / REVIEWED).parent.mkdir(parents=True)
    (tmp_path / REVIEWED).write_bytes((ROOT / REVIEWED).read_bytes())
    return directory


def test_reviewed_missing_license_is_included_with_pinned_provenance(
    frontend: Path,
) -> None:
    document, machine = generate(frontend.parent, frontend=frontend)
    license_text = (ROOT / REVIEWED).read_text().strip()
    assert license_text in document.decode()
    assert COMPILER_RUNTIME_SOURCE in document.decode()
    entry = json.loads(machine)["packages"][0]
    assert entry["license_source"] == COMPILER_RUNTIME_SOURCE
    assert entry["license_sha256"] == hashlib.sha256(license_text.encode()).hexdigest()
    assert entry["selected_license"] == "MIT"


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("package", "name", "another-runtime"),
        ("package", "version", "1.0.1"),
        ("package", "license", "ISC"),
        ("lock", "integrity", "sha512-unreviewed"),
        ("lock", "resolved", "https://example.invalid/unreviewed.tgz"),
    ],
)
def test_missing_license_exception_rejects_unreviewed_packages(
    frontend: Path, target: str, field: str, value: str
) -> None:
    path = frontend / (
        "node_modules/react-compiler-runtime/package.json"
        if target == "package"
        else "package-lock.json"
    )
    data = json.loads(path.read_text())
    entry = (
        data
        if target == "package"
        else data["packages"]["node_modules/react-compiler-runtime"]
    )
    entry[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="No license text found"):
        generate(frontend.parent, frontend=frontend)


@pytest.mark.parametrize("missing", [False, True])
def test_reviewed_license_cannot_be_changed_or_removed(
    frontend: Path, missing: bool
) -> None:
    path = frontend.parent / REVIEWED
    if missing:
        path.unlink()
    else:
        path.write_text("changed license")
    with pytest.raises(SystemExit, match="license is missing or changed"):
        generate(frontend.parent, frontend=frontend)


def test_package_license_takes_precedence_over_reviewed_copy(frontend: Path) -> None:
    (frontend / "node_modules/react-compiler-runtime/LICENSE").write_text(
        "Package notice"
    )
    (frontend.parent / REVIEWED).unlink()
    document, machine = generate(frontend.parent, frontend=frontend)
    assert "Package notice" in document.decode()
    assert "license_source" not in json.loads(machine)["packages"][0]


def test_future_versions_require_their_own_license(frontend: Path) -> None:
    for name in (
        "node_modules/react-compiler-runtime/package.json",
        "package-lock.json",
        "build/bundled-packages.json",
    ):
        path = frontend / name
        path.write_text(path.read_text().replace("1.0.0", "1.0.1"))
    with pytest.raises(SystemExit, match="No license text found"):
        generate(frontend.parent, frontend=frontend)
