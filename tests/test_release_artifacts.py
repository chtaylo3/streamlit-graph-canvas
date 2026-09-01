import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from ci.verify_release_artifacts import compare_wheels, safe_extract_sdist


def _sdist(path: Path, members: list[tuple[str, bytes, str]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside"
                info.size = 0
                archive.addfile(info)
            else:
                archive.addfile(info, io.BytesIO(content))


def test_safe_sdist_extraction_accepts_regular_single_root(tmp_path: Path) -> None:
    archive = tmp_path / "valid.tar.gz"
    _sdist(archive, [("project-1.0/pyproject.toml", b"[project]\n", "file")])

    root = safe_extract_sdist(archive, tmp_path / "output")

    assert root == tmp_path / "output/project-1.0"
    assert (root / "pyproject.toml").read_bytes() == b"[project]\n"


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside", "file"),
        ("/absolute", "file"),
        ("project/link", "symlink"),
    ],
)
def test_safe_sdist_extraction_rejects_hostile_members(
    tmp_path: Path, name: str, kind: str
) -> None:
    archive = tmp_path / "hostile.tar.gz"
    _sdist(archive, [(name, b"bad", kind)])

    with pytest.raises(ValueError):
        safe_extract_sdist(archive, tmp_path / "output")


def _wheel(path: Path, body: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("package/__init__.py", body)
        archive.writestr("package-1.0.dist-info/METADATA", b"Name: package\n")
        archive.writestr("package-1.0.dist-info/RECORD", b"ignored")


def test_wheel_comparison_ignores_record_but_rejects_code_change(
    tmp_path: Path,
) -> None:
    direct = tmp_path / "direct.whl"
    same = tmp_path / "same.whl"
    changed = tmp_path / "changed.whl"
    _wheel(direct, b"value = 1\n")
    _wheel(same, b"value = 1\n")
    _wheel(changed, b"value = 2\n")

    compare_wheels(direct, same)
    with pytest.raises(ValueError, match="contents differ"):
        compare_wheels(direct, changed)
