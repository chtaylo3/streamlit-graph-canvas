"""Report the whole advisory probe, including stages after frontend generation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def build_report(
    surface: str, outcome: str, stage: str, artifacts: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    status = {"success": "passed", "failure": "failed"}.get(outcome, "not_tested")
    selections = []
    errors = []
    for name, evidence in artifacts.items():
        selections.extend(evidence.get("selections", []))
        if evidence.get("status") == "failed":
            errors.append({"artifact": name, "error": evidence.get("error")})
            if stage in {"python-probe", "frontend-probe", "python-environment"}:
                stage = evidence.get("stage", stage)
    # A generated frontend is not proof that wheel installation or browsers ran.
    if status == "passed":
        expected = {"candidate.json": "passed"}
        if surface == "browser":
            expected["candidate-browser.json"] = "prepared"
        if any(
            artifacts.get(name, {}).get("status") != value
            for name, value in expected.items()
        ):
            status = "failed"
            errors.append(
                {"error": "successful probe has missing or failed stage evidence"}
            )
    if status == "failed" and not errors:
        errors.append(
            {"error": f"{stage or 'probe'} failed; see job log and test artifacts"}
        )
    return {
        "surface": surface,
        "status": status,
        "stage": stage or "not_started",
        "support_promoted": False,
        "selections": selections,
        "errors": errors,
        "artifacts": {
            name: {k: value.get(k) for k in ("status", "stage")}
            for name, value in artifacts.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--surface", choices=("python", "frontend", "browser"), required=True
    )
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--stage", default="")
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    args = parser.parse_args()
    artifacts = {}
    for name in ("candidate.json", "candidate-browser.json"):
        path = args.directory / name
        if path.exists():
            try:
                artifacts[name] = json.loads(path.read_text())
            except (ValueError, OSError) as error:
                artifacts[name] = {
                    "status": "failed",
                    "stage": "reporting",
                    "error": str(error),
                }
    report = build_report(args.surface, args.outcome, args.stage, artifacts)
    (args.directory / "candidate-outcome.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    lines = [
        f"### Latest tested: {args.surface} — {report['status']} (advisory)",
        f"Stage: `{report['stage']}`. Support endpoints were not promoted.",
        "See `candidate-outcome.json` and stage artifacts for errors "
        "and resolved inventories.",
    ]
    if report["selections"]:
        lines.extend(
            [
                "",
                "| Package | Selected | Decision | Cooldown eligibility (UTC) |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in report["selections"]:
            lines.append(
                f"| {item['package']} | {item.get('selected', '—')} | "
                f"{item.get('reason', 'selection failed')} | "
                f"{item.get('eligible_at', item.get('baseline_eligible_at', '—'))} |"
            )
    summary = "\n".join(lines) + "\n"
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a") as stream:
            stream.write(summary)
    if report["status"] != "passed":
        print(
            f"::warning::Advisory {args.surface} probe {report['status']}; "
            "see candidate-outcome.json."
        )
    if args.outcome == "success" and report["status"] != "passed":
        raise SystemExit("probe outcome contradicts stage evidence")


if __name__ == "__main__":
    main()
