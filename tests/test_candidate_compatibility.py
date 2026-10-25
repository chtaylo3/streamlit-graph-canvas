from __future__ import annotations

import datetime as dt
import io
import json
import sys

import pytest

from ci import build_conformance_environment, candidate_versions, run_compatibility
from ci.candidate_versions import candidate_version, select_release
from ci.report_candidate_outcome import build_report

NOW = dt.datetime(2026, 10, 24, 20, tzinfo=dt.UTC)


def test_react_flow_probe_keeps_stable_companions_and_locked_tools():
    from pathlib import Path

    root = Path(__file__).parents[1]
    frontend = root / "packages/core/src/streamlit_graph_canvas/frontend"
    package = json.loads((frontend / "package.json").read_text())
    lock = json.loads((frontend / "package-lock.json").read_text())
    policy = run_compatibility.load_policy(root)
    specs = run_compatibility.npm_specs(
        policy, "forward", "react-flow-stable", package=package, lock=lock
    )
    selected = dict(spec.rsplit("@", 1) for spec in specs)
    assert (
        selected["@xyflow/react"]
        == policy["npm"]["runtime"]["@xyflow/react"]["forward"]
    )
    for name in ("react", "react-dom", "elkjs", "@streamlit/component-v2-lib"):
        assert selected[name] == policy["npm"]["runtime"][name]["latest_supported"]
    for name in package["devDependencies"]:
        assert selected[name] == lock["packages"]["node_modules/" + name]["version"]
    assert any(
        "canary" in spec
        for spec in run_compatibility.npm_specs(policy, "forward", "react-flow")
    )
    with pytest.raises(ValueError, match="requires the forward lane"):
        run_compatibility.npm_specs(policy, "minimum", "react-flow-stable")


def test_stable_react_probe_rejects_invalid_peers_before_tests_or_build(
    tmp_path, monkeypatch
):
    from pathlib import Path
    from types import SimpleNamespace

    root = Path(__file__).parents[1]
    calls = []
    monkeypatch.setattr(
        run_compatibility, "run", lambda command, **kwargs: calls.append(command)
    )
    monkeypatch.setattr(
        run_compatibility.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="invalid peer tree"
        ),
    )
    args = SimpleNamespace(
        root=root,
        lane="forward",
        scenario="react-flow-stable",
        selections=[],
        output=tmp_path / "report.json",
    )
    with pytest.raises(SystemExit, match="dependency tree is invalid"):
        run_compatibility.frontend_lane(args, run_compatibility.load_policy(root))
    assert args.stage == "dependency-validation"
    assert calls == [["npm", "install", "--legacy-peer-deps"]]


def test_fresh_approved_baseline_does_not_block_or_downgrade_candidates():
    releases = {
        "1.0.0": "2026-09-01T00:00:00Z",
        "1.1.0": "2026-10-21T00:00:00Z",
        "1.2.0": "2026-10-23T00:00:00Z",
    }
    assert (
        select_release(releases, now=NOW, minimum="1.0.0", baseline="1.1.0") == "1.1.0"
    )
    releases["1.3.0"] = "2026-10-16T00:00:00Z"
    assert (
        select_release(releases, now=NOW, minimum="1.0.0", baseline="1.1.0") == "1.3.0"
    )


@pytest.mark.parametrize(
    ("baseline", "releases"),
    [
        ("1.0.0", {}),
        ("1.0.0", {"1.0.0": "2026-10-25T00:00:00Z"}),
        ("1.0.0rc1", {"1.0.0rc1": "2026-10-21T00:00:00Z"}),
        ("1.0.0.dev1", {"1.0.0.dev1": "2026-10-21T00:00:00Z"}),
    ],
)
def test_baseline_exception_cannot_admit_missing_future_or_unstable_versions(
    baseline, releases
):
    with pytest.raises(ValueError, match="no stable"):
        select_release(releases, now=NOW, minimum=baseline, baseline=baseline)


@pytest.mark.parametrize("ecosystem", ["python", "npm"])
@pytest.mark.parametrize("excluded", [False, True])
def test_registry_selection_records_baseline_and_rejects_withdrawn_releases(
    monkeypatch, ecosystem, excluded
):
    released = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat()
    if ecosystem == "python":
        data = {
            "releases": {
                "1.0.0": [{"upload_time_iso_8601": released, "yanked": excluded}]
            }
        }
    else:
        data = {
            "time": {"1.0.0": released},
            "versions": {"1.0.0": {"deprecated": "withdrawn"} if excluded else {}},
        }
    monkeypatch.setattr(
        candidate_versions.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(data).encode()),
    )
    evidence = []
    if excluded:
        with pytest.raises(ValueError, match=f"{ecosystem} sample"):
            candidate_version(
                ecosystem, "sample", "1.0.0", baseline="1.0.0", selections=evidence
            )
        assert evidence[0]["status"] == "failed"
        assert "error" in evidence[0]
    else:
        assert (
            candidate_version(
                ecosystem, "sample", "1.0.0", baseline="1.0.0", selections=evidence
            )
            == "1.0.0"
        )
        assert evidence[0]["reason"] == "approved_baseline_retained"
        assert evidence[0]["selected"] == "1.0.0"
        assert evidence[0]["baseline_released_at"] == released
        assert dt.datetime.fromisoformat(evidence[0]["eligible_at"]) > dt.datetime.now(
            dt.UTC
        )


def test_python_and_frontend_use_approved_baselines_without_changing_policy(
    monkeypatch,
):
    calls = []

    def select(ecosystem, name, minimum, *, baseline, selections):
        calls.append((name, baseline))
        return baseline

    monkeypatch.setattr(run_compatibility, "candidate_version", select)
    entry = {"minimum": "1.0.0", "latest_supported": "1.1.0"}
    policy = {"python": {"sample": entry}, "npm": {"runtime": {"sample": entry}}}
    assert run_compatibility.python_specs(policy, "latest-tested") == ["sample==1.1.0"]
    assert run_compatibility.npm_specs(
        policy,
        "latest-tested",
        "all",
        package={
            "dependencies": {"sample": "^1.0.0"},
            "devDependencies": {"tool": "^2.0.0"},
        },
        lock={
            "packages": {
                "node_modules/sample": {"version": "1.2.0"},
                "node_modules/tool": {"version": "2.1.0"},
            }
        },
    ) == ["sample@1.2.0", "tool@2.1.0"]
    assert calls == [("sample", "1.1.0"), ("sample", "1.2.0"), ("tool", "2.1.0")]
    assert entry == {"minimum": "1.0.0", "latest_supported": "1.1.0"}


@pytest.mark.parametrize("surface", ["python", "frontend"])
def test_failed_probe_preserves_selection_stage_and_package_evidence(
    monkeypatch, tmp_path, surface
):
    output = tmp_path / "nested" / "candidate.json"

    def fail(args, policy):
        args.stage = "candidate-selection"
        args.selections.append({"package": "sample", "status": "failed"})
        raise ValueError("sample registry failure")

    monkeypatch.setattr(run_compatibility, f"{surface}_lane", fail)
    argv = ["probe", surface, "--lane", "latest-tested", "--output", str(output)]
    if surface == "python":
        argv.extend(["--python", "3.12", "--venv", str(tmp_path / "env")])
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(ValueError, match="sample registry"):
        run_compatibility.main()
    evidence = json.loads(output.read_text())
    assert evidence["status"] == "failed"
    assert evidence["stage"] == "candidate-selection"
    assert evidence["selections"][0]["package"] == "sample"
    assert evidence["support_promoted"] is False


def test_browser_environment_failure_is_saved_without_stale_success(
    monkeypatch, tmp_path
):
    output = tmp_path / "candidate-browser.json"
    output.write_text('{"status":"prepared"}')

    def fail(args):
        args.output.unlink()
        args.stage = "candidate-installation"
        args.selections.append({"package": "sample", "selected": "2.0.0"})
        raise SystemExit("incompatible candidates")

    monkeypatch.setattr(build_conformance_environment, "build_environment", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--set",
            "transports",
            "--wheelhouse",
            str(tmp_path),
            "--venv",
            str(tmp_path / "env"),
            "--dependency-lane",
            "latest-tested",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit, match="incompatible"):
        build_conformance_environment.main()
    evidence = json.loads(output.read_text())
    assert evidence["status"] == "failed"
    assert evidence["stage"] == "candidate-installation"


@pytest.mark.parametrize("stage", ["wheel-build", "browser-tools", "browser-tests"])
def test_frontend_success_does_not_mask_later_browser_failure(stage):
    report = build_report(
        "browser",
        "failure",
        stage,
        {"candidate.json": {"status": "passed", "stage": "artifact-generation"}},
    )
    assert report["status"] == "failed"
    assert report["stage"] == stage
    assert stage in report["errors"][0]["error"]


def test_report_requires_all_stages_and_distinguishes_not_tested():
    artifacts = {"candidate.json": {"status": "passed"}}
    assert (
        build_report("browser", "success", "browser-tests", artifacts)["status"]
        == "failed"
    )
    artifacts["candidate-browser.json"] = {"status": "prepared"}
    assert (
        build_report("browser", "success", "browser-tests", artifacts)["status"]
        == "passed"
    )
    assert build_report("python", "skipped", "", {})["status"] == "not_tested"


def test_report_writes_machine_outcome_and_summary(monkeypatch, tmp_path):
    from ci.report_candidate_outcome import main

    (tmp_path / "candidate.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "stage": "candidate-selection",
                "error": "sample missing",
                "selections": [{"package": "sample", "status": "failed"}],
            }
        )
    )
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report",
            "--surface",
            "frontend",
            "--outcome",
            "failure",
            "--stage",
            "frontend-probe",
            "--directory",
            str(tmp_path),
        ],
    )
    main()
    report = json.loads((tmp_path / "candidate-outcome.json").read_text())
    assert report["stage"] == "candidate-selection"
    assert report["status"] == "failed"
    assert "frontend — failed" in summary.read_text()
    assert "sample" in summary.read_text()
