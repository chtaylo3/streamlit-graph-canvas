import hashlib
from pathlib import Path

import pytest

from ci.stage_release_bundle import stage


def test_release_bundle_binds_and_hashes_publishable_artifacts(
    tmp_path: Path,
) -> None:
    verified = tmp_path / "verified"
    verified.mkdir()
    for name in (
        "core-1.whl",
        "core-1.tar.gz",
        "contrib-1.whl",
        "contrib-1.tar.gz",
    ):
        (verified / name).write_bytes(name.encode())
    (verified / "core.cdx.json").write_text("{}\n", encoding="utf-8")
    output = tmp_path / "bundle"

    stage(
        verified,
        output,
        repository="owner/repo",
        run_id="42",
        sha="a" * 40,
        tag="v1.0.0",
    )

    lines = (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert digest == hashlib.sha256((output / relative).read_bytes()).hexdigest()


def test_release_bundle_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    with pytest.raises(ValueError, match="refusing"):
        stage(
            tmp_path,
            output,
            repository="owner/repo",
            run_id="42",
            sha="a" * 40,
            tag="v1.0.0",
        )
