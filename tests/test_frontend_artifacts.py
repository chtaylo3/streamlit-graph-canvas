from pathlib import Path

from ci.generate_frontend_artifacts import artifact_differences


def test_artifact_diff_reports_missing_changed_and_obsolete() -> None:
    expected = {
        Path("build/index-new.js"): b"new",
        Path("build/index.css"): b"css",
    }
    actual = {
        Path("build/index-new.js"): b"stale",
        Path("build/index-old.js"): b"old",
    }

    assert artifact_differences(expected, actual) == {
        "missing": ["build/index.css"],
        "obsolete": ["build/index-old.js"],
        "changed": ["build/index-new.js"],
    }
