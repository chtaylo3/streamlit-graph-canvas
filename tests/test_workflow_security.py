from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ci.verify_workflow_security import APP_TOKEN, DOWNLOAD, verify_workflows

ROOT = Path(__file__).parents[1]


def write_workflow(directory: Path, body: str) -> None:
    directory.mkdir()
    (directory / "test.yml").write_text(body, encoding="utf-8")


def test_repository_workflows_keep_publication_fail_closed() -> None:
    assert verify_workflows(ROOT / ".github/workflows") == []


@pytest.mark.parametrize(
    ("workflow", "approved", "message"),
    [
        ("dependency-publish.yml", APP_TOKEN, "App action differs from allowlist"),
        ("release.yml", DOWNLOAD, "privileged actions differ from the allowlist"),
    ],
)
def test_privileged_action_updates_still_require_exact_reviewed_pins(
    tmp_path: Path, workflow: str, approved: str, message: str
) -> None:
    directory = tmp_path / "workflows"
    shutil.copytree(ROOT / ".github/workflows", directory)
    path = directory / workflow
    unreviewed = approved.split("@", 1)[0] + "@" + "0" * 40
    path.write_text(path.read_text().replace(approved, unreviewed))
    assert any(message in error for error in verify_workflows(directory))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            '--attempt "$SOURCE_ATTEMPT" --commit',
            '--attempt "$SOURCE_ATTEMPT" --commit && npm install',
        ),
        ("permission-contents: write", "permission-contents: read"),
        ("permission-pull-requests: read", "permission-pull-requests: write"),
        ("vars.DEPENDENCY_PREPARATION_WRITE == 'true'", "always()"),
        (
            "persist-credentials: false",
            "persist-credentials: false\n          ref: attacker",
        ),
    ],
)
def test_dependency_publisher_rejects_privilege_boundary_changes(tmp_path, old, new):
    directory = tmp_path / "workflows"
    directory.mkdir()
    source = (ROOT / ".github/workflows/dependency-publish.yml").read_text()
    assert old in source
    (directory / "dependency-publish.yml").write_text(source.replace(old, new))
    assert verify_workflows(directory)


def test_candidate_failures_are_advisory_and_supported_matrix_stays_blocking():
    import yaml

    candidate = yaml.safe_load(
        (ROOT / ".github/workflows/candidate-compatibility.yml").read_text()
    )
    probe = next(
        step
        for step in candidate["jobs"]["latest-tested"]["steps"]
        if step.get("id") == "probe"
    )
    assert not probe.get("continue-on-error", False)
    assert candidate["jobs"]["latest-tested"]["continue-on-error"] is True
    reporting = next(
        step
        for step in candidate["jobs"]["latest-tested"]["steps"]
        if "report_candidate_outcome.py" in step.get("run", "")
    )
    assert reporting["if"] == "always()"
    assert reporting["env"]["OUTCOME"] == "${{ steps.probe.outcome }}"
    assert candidate["permissions"] == {"contents": "read"}
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for name in [
        "python-compatibility",
        "frontend-compatibility",
        "chromium-compatibility",
    ]:
        assert not ci["jobs"][name].get("continue-on-error", False)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "permissions:\n  id-token: write\njobs: {}\n",
            "workflow-level id-token: write",
        ),
        (
            "jobs:\n  release:\n    permissions:\n      id-token: write\n",
            "release: id-token: write",
        ),
        (
            "jobs:\n  release:\n    environment: pypi\n",
            "only the publisher may use pypi",
        ),
        (
            "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@abc\n",
            "persist-credentials: false",
        ),
        (
            "jobs:\n  release:\n    steps:\n      - run: uv publish dist/*\n",
            "uv publish is forbidden",
        ),
        (
            "jobs:\n  release:\n    steps:\n"
            "      - uses: pypa/gh-action-pypi-publish@abc\n",
            "privileged release action is misplaced",
        ),
        (
            "jobs:\n  test:\n    env:\n      TEMP_PATH: ${{ runner.temp }}/output\n",
            "job env TEMP_PATH cannot use the runner context",
        ),
    ],
)
def test_workflow_security_guard_rejects_unsafe_mutations(
    tmp_path: Path, body: str, message: str
) -> None:
    directory = tmp_path / "workflows"
    write_workflow(directory, body)
    assert any(message in error for error in verify_workflows(directory))


def test_workflow_security_guard_accepts_hardened_checkout(tmp_path: Path) -> None:
    directory = tmp_path / "workflows"
    write_workflow(
        directory,
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - uses: actions/checkout@abc\n"
        "        with:\n"
        "          persist-credentials: false\n",
    )
    assert verify_workflows(directory) == []


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "cd release-bundle && sha256sum --check SHA256SUMS",
            "python ci/check.py",
            "fixed SHA256 verification",
        ),
        (
            "release-bundle-${{ github.run_id }}-${{ github.sha }}-"
            "${{ github.ref_name }}",
            "release-bundle-${{ github.run_id }}",
            "run/SHA/tag binding",
        ),
        (
            "actions: read\n      id-token: write\n      attestations: write",
            "actions: read\n      contents: read\n      id-token: write\n"
            "      attestations: write",
            "privileged permissions",
        ),
    ],
)
def test_release_privilege_topology_rejects_mutations(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    body = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert old in body
    directory = tmp_path / "workflows"
    directory.mkdir()
    (directory / "release.yml").write_text(body.replace(old, new), encoding="utf-8")
    assert any(message in error for error in verify_workflows(directory))
