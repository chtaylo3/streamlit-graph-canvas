"""Structurally enforce workflow privilege and release publication boundaries."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

DOWNLOAD = "actions/download-artifact@634f93cb2916e3fdff6788551b99b062d0335ce0"
ATTEST = "actions/attest-build-provenance@977bb373ede98d70efdf65b84cb5f73e068dcc2a"
PUBLISH = "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
DIGEST = "cd release-bundle && sha256sum --check SHA256SUMS"
PUBLISH_COMMAND = re.compile(r"(?:^|\s)uv\s+publish(?:\s|$)")
RUNNER_CONTEXT = re.compile(r"\$\{\{[^}]*\brunner\.")


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _permissions(value: object) -> dict[str, str]:
    return {str(key): str(item).casefold() for key, item in _mapping(value).items()}


def _environment(value: object) -> str:
    if isinstance(value, str):
        return value.casefold()
    name = _mapping(value).get("name")
    return name.casefold() if isinstance(name, str) else ""


def _steps(
    job: dict[str, Any], subject: str, errors: list[str]
) -> list[dict[str, Any]]:
    raw = job.get("steps", [])
    if not isinstance(raw, list):
        errors.append(f"{subject}: steps must be a list")
        return []
    return [_mapping(step) for step in raw]


def _verify_privileged(
    name: str, job: dict[str, Any], subject: str, errors: list[str]
) -> None:
    expected_permissions = (
        {"actions": "read", "id-token": "write", "attestations": "write"}
        if name == "attest"
        else {"actions": "read", "id-token": "write"}
    )
    if _permissions(job.get("permissions")) != expected_permissions:
        errors.append(
            f"{subject}: privileged permissions must be exactly {expected_permissions}"
        )
    if name == "attest" and _environment(job.get("environment")):
        errors.append(f"{subject}: attestation job must not have an environment")
    if name == "publish" and _environment(job.get("environment")) != "pypi":
        errors.append(f"{subject}: publisher must use the pypi environment")
    steps = _steps(job, subject, errors)
    expected_action = ATTEST if name == "attest" else PUBLISH
    if len(steps) != 3:
        errors.append(f"{subject}: privileged job must have exactly three steps")
        return
    actions = [step.get("uses") for step in steps if "uses" in step]
    commands = [step.get("run") for step in steps if "run" in step]
    if actions != [DOWNLOAD, expected_action]:
        errors.append(f"{subject}: privileged actions differ from the allowlist")
    if [" ".join(str(command).split()) for command in commands] != [DIGEST]:
        errors.append(f"{subject}: only the fixed SHA256 verification is allowed")
    artifact = _mapping(steps[0].get("with")).get("name")
    if not isinstance(artifact, str) or any(
        binding not in artifact
        for binding in ("github.run_id", "github.sha", "github.ref_name")
    ):
        errors.append(f"{subject}: downloaded artifact lacks run/SHA/tag binding")
    final_inputs = _mapping(steps[2].get("with"))
    if name == "attest" and final_inputs.get("subject-path") != (
        "release-bundle/publish/*"
    ):
        errors.append(f"{subject}: attestation subject path is not publish-only")
    if name == "publish" and final_inputs.get("packages-dir") != (
        "release-bundle/publish/"
    ):
        errors.append(f"{subject}: publisher package directory is not publish-only")


def verify_workflows(directory: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(directory.glob("*.yml")):
        try:
            workflow = _mapping(
                yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            )
        except yaml.YAMLError as error:
            errors.append(f"{path.name}: invalid workflow YAML: {error}")
            continue
        if _permissions(workflow.get("permissions")).get("id-token") == "write":
            errors.append(f"{path.name}: workflow-level id-token: write is forbidden")
        for job_name, raw_job in _mapping(workflow.get("jobs")).items():
            job = _mapping(raw_job)
            subject = f"{path.name}:{job_name}"
            for key, value in _mapping(job.get("env")).items():
                if isinstance(value, str) and RUNNER_CONTEXT.search(value):
                    errors.append(
                        f"{subject}: job env {key} cannot use the runner context"
                    )
            privileged = path.name == "release.yml" and job_name in {
                "attest",
                "publish",
            }
            if (
                _permissions(job.get("permissions")).get("id-token") == "write"
                and not privileged
            ):
                errors.append(f"{subject}: id-token: write is forbidden")
            if privileged:
                _verify_privileged(job_name, job, subject, errors)
            elif _environment(job.get("environment")) == "pypi":
                errors.append(f"{subject}: only the publisher may use pypi")
            for index, step in enumerate(_steps(job, subject, errors), start=1):
                step_subject = f"{subject}:step-{index}"
                action = step.get("uses")
                if isinstance(action, str) and action.startswith("actions/checkout@"):
                    persist = _mapping(step.get("with")).get("persist-credentials")
                    if not isinstance(persist, str) or persist.casefold() != "false":
                        errors.append(
                            f"{step_subject}: checkout must set "
                            "persist-credentials: false"
                        )
                if (
                    isinstance(action, str)
                    and action.startswith(
                        (
                            "actions/attest-build-provenance@",
                            "pypa/gh-action-pypi-publish@",
                        )
                    )
                    and (not privileged or action not in {ATTEST, PUBLISH})
                ):
                    errors.append(
                        f"{step_subject}: privileged release action is misplaced"
                    )
                command = step.get("run")
                if isinstance(command, str) and PUBLISH_COMMAND.search(command):
                    errors.append(f"{step_subject}: uv publish is forbidden")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflows",
        type=Path,
        default=Path(__file__).parents[1] / ".github/workflows",
    )
    args = parser.parse_args()
    errors = verify_workflows(args.workflows)
    if errors:
        raise SystemExit("workflow security violations:\n- " + "\n- ".join(errors))
    print("workflow security boundary is fail-closed")


if __name__ == "__main__":
    main()
