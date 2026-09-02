from pathlib import Path

import pytest
from packaging.version import InvalidVersion

from ci.verify_release_tag import verify_release_tag


def write_version(root: Path, version: str) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "release-tag-test"\nversion = "{version}"\n',
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "version",
    ["0.1.0a1", "0.1.0b1", "0.1.0rc1", "0.1.0"],
)
def test_publishable_versions_are_accepted(tmp_path: Path, version: str) -> None:
    write_version(tmp_path, version)

    verify_release_tag(f"v{version}", tmp_path)


@pytest.mark.parametrize("version", ["0.1.0.dev0", "0.1.0.dev1"])
def test_development_versions_are_rejected(tmp_path: Path, version: str) -> None:
    write_version(tmp_path, version)

    with pytest.raises(ValueError, match="may be built by CI but not published"):
        verify_release_tag(f"v{version}", tmp_path)


def test_tag_must_match_source_version(tmp_path: Path) -> None:
    write_version(tmp_path, "0.1.0rc1")

    with pytest.raises(ValueError, match="does not match project version"):
        verify_release_tag("v0.1.0rc2", tmp_path)


def test_malformed_version_is_rejected(tmp_path: Path) -> None:
    write_version(tmp_path, "not a version")

    with pytest.raises(InvalidVersion):
        verify_release_tag("vnot a version", tmp_path)
