from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import io
import json
import zipfile

import pytest

from ci.candidate_versions import select_release
from ci.prepare_dependency_pr import FRONTEND, normalize_manifest, validate_npm_sources
from ci.publish_dependency_pr import (
    commit_input,
    read_payload,
    validate_payload,
    verify_commit_provenance,
    verify_context,
    verify_manifest_outputs,
    verify_source_manifests,
)
from ci.run_compatibility import npm_specs, python_specs


def payload() -> dict:
    content = b"generated bundle"
    return {
        "schema": 1,
        "base": "a" * 40,
        "head": "b" * 40,
        "files": [
            {
                "path": f"{FRONTEND}/build/index-abc.js",
                "content": base64.b64encode(content).decode(),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }


def test_cooldown_excludes_fresh_and_prerelease_candidates() -> None:
    releases = {
        "1.1.0": "2026-09-01T00:00:00Z",
        "1.2.0": "2026-09-05T00:00:00Z",
        "2.0.0": "2026-09-06T00:00:00Z",
        "3.0.0rc1": "2026-08-01T00:00:00Z",
        "4.0.0": "not a date",
    }
    assert (
        select_release(
            releases, now=dt.datetime(2026, 9, 12, tzinfo=dt.UTC), minimum="1.0.0"
        )
        == "1.2.0"
    )
    with pytest.raises(ValueError, match="no stable"):
        select_release(
            releases, now=dt.datetime(2026, 9, 12, tzinfo=dt.UTC), minimum="2.0.0"
        )


def test_supported_and_candidate_lanes_are_independent(monkeypatch) -> None:
    entry = {"minimum": "1.0.0", "supported": ">=1.0.0,<2", "latest_supported": "1.2.0"}
    policy = {
        "python": {"sample": entry},
        "npm": {"runtime": {"sample": {**entry, "supported": "^1.0.0"}}, "build": {}},
    }
    before = copy.deepcopy(policy)
    monkeypatch.setattr("ci.run_compatibility.candidate_version", lambda *args: "2.0.0")
    assert python_specs(policy, "latest-supported") == ["sample==1.2.0"]
    assert python_specs(policy, "latest-tested") == ["sample==2.0.0"]
    assert npm_specs(policy, "latest-supported", "all") == ["sample@1.2.0"]
    assert npm_specs(policy, "latest-tested", "all") == ["sample@2.0.0"]
    assert policy == before


def test_normalization_preserves_support_without_changing_locked_version() -> None:
    base = {"dependencies": {"sample": "^1.0.0"}, "devDependencies": {}}
    candidate = {"dependencies": {"sample": "^1.3.0"}, "devDependencies": {}}
    lock = {"packages": {"node_modules/sample": {"version": "1.3.0"}}}
    assert normalize_manifest(base, candidate, lock) == base
    assert lock["packages"]["node_modules/sample"]["version"] == "1.3.0"
    assert normalize_manifest(base, base, lock) == base
    lock["packages"]["node_modules/sample"]["version"] = "2.0.0"
    with pytest.raises(ValueError, match="policy review"):
        normalize_manifest(base, candidate, lock)


def test_manifest_script_injection_requires_review() -> None:
    base = {"dependencies": {}, "devDependencies": {}}
    with pytest.raises(ValueError, match="non-dependency"):
        normalize_manifest(
            base, {**base, "scripts": {"postinstall": "bad"}}, {"packages": {}}
        )


@pytest.mark.parametrize(
    "name",
    [
        "../ci/run.py",
        "/tmp/evil",
        ".github/workflows/ci.yml",
        "ci/dependency-policy.toml",
        f"{FRONTEND}/build/../../evil.js",
    ],
)
def test_publisher_rejects_unapproved_paths(name) -> None:
    data = payload()
    data["files"][0]["path"] = name
    with pytest.raises(ValueError, match="path"):
        validate_payload(data)


def test_payload_integrity_duplicates_and_deletions() -> None:
    data = payload()
    validate_payload(data)
    data["files"].append(data["files"][0])
    with pytest.raises(ValueError, match="path"):
        validate_payload(data)
    data = payload()
    data["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="bytes"):
        validate_payload(data)
    data["files"][0].update(content=None, sha256=None)
    validate_payload(data)
    data["files"][0]["path"] = f"{FRONTEND}/package.json"
    with pytest.raises(ValueError, match="deleted"):
        validate_payload(data)


@pytest.mark.parametrize("name", ["../prepared.json", "/prepared.json", "script.py"])
def test_artifact_never_extracts_unexpected_files(name) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, json.dumps(payload()))
    with pytest.raises(ValueError, match=r"only prepared\.json"):
        read_payload(stream.getvalue())


def test_valid_artifact_and_atomic_commit_identity() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("prepared.json", json.dumps(payload()))
    data = read_payload(stream.getvalue())
    pr = {
        "base": {"sha": "a" * 40},
        "head": {"sha": "b" * 40, "ref": "dependabot/sample"},
    }
    mutation = commit_input("owner/repo", pr, data)
    assert mutation["expectedHeadOid"] == "b" * 40
    assert mutation["branch"]["branchName"] == "dependabot/sample"
    pr["head"]["sha"] = "c" * 40
    with pytest.raises(ValueError, match="stale"):
        commit_input("owner/repo", pr, data)

    pr["head"]["sha"] = "b" * 40
    pr["base"]["sha"] = "c" * 40
    with pytest.raises(ValueError, match="stale"):
        commit_input("owner/repo", pr, data)


@pytest.mark.parametrize(
    "alter", ["event", "attempt", "fork", "head", "author", "signature", "files"]
)
def test_publisher_rejects_forged_or_stale_github_context(monkeypatch, alter) -> None:
    run = {
        "event": "pull_request",
        "conclusion": "success",
        "run_attempt": 1,
        "workflow_id": 2,
        "head_repository": {"full_name": "owner/repo"},
        "pull_requests": [{"number": 3}],
        "head_sha": "b" * 40,
    }
    pr = {
        "state": "open",
        "user": {"login": "dependabot[bot]"},
        "base": {"ref": "main", "sha": "a" * 40},
        "head": {"sha": "b" * 40, "repo": {"full_name": "owner/repo"}},
        "commits": 1,
        "changed_files": 1,
        "number": 3,
    }
    commits = [
        {
            "node_id": "node1",
            "sha": "b" * 40,
            "author": {"login": "dependabot[bot]"},
            "commit": {"verification": {"verified": True}},
        }
    ]
    files = [{"filename": "uv.lock"}]

    def mock_api(path, body=None):
        if path == "graphql":
            return {"data": {"nodes": [bot_signature()]}}
        if path.endswith("/runs/1"):
            return run
        if "/workflows/" in path:
            return {"id": 2}
        if "/commits?" in path:
            return commits
        if "/files?" in path:
            return files
        return pr

    monkeypatch.setattr("ci.publish_dependency_pr.api", mock_api)
    verify_context("owner/repo", 1, 1, "")
    if alter == "event":
        run["event"] = "push"
    elif alter == "attempt":
        run["run_attempt"] = 2
    elif alter == "fork":
        pr["head"]["repo"]["full_name"] = "attacker/repo"
    elif alter == "head":
        pr["head"]["sha"] = "c" * 40
    elif alter == "author":
        commits[0]["author"]["login"] = "attacker"
    elif alter == "signature":
        commits[0]["commit"]["verification"]["verified"] = False
    else:
        files[0]["filename"] = "ci/prepare_dependency_pr.py"
    with pytest.raises(ValueError):
        verify_context("owner/repo", 1, 1, "")


def test_publisher_does_not_trust_generated_manifest_scripts(monkeypatch) -> None:
    original = {"dependencies": {"sample": "^1.0.0"}}
    monkeypatch.setattr(
        "ci.publish_dependency_pr.api",
        lambda path: {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(
                b"[npm.build]\n[npm.test]\n"
                if "ci/dependency-policy.toml" in path
                else json.dumps(original).encode()
            ).decode(),
        },
    )
    data = payload()
    data["files"][0]["path"] = f"{FRONTEND}/package.json"
    data["files"][0]["content"] = base64.b64encode(
        json.dumps(original).encode()
    ).decode()
    verify_manifest_outputs("owner/repo", data)
    malicious = {**original, "scripts": {"postinstall": "steal-credentials"}}
    data["files"][0]["content"] = base64.b64encode(
        json.dumps(malicious).encode()
    ).decode()
    with pytest.raises(ValueError, match="scripts"):
        verify_manifest_outputs("owner/repo", data)


def test_exact_tool_upgrade_preserved_but_runtime_pin_requires_review() -> None:
    base = {
        "dependencies": {"sample": "1.0.0"},
        "devDependencies": {"prettier": "3.6.2"},
    }
    candidate = {**base, "devDependencies": {"prettier": "3.9.6"}}
    lock = {"packages": {"node_modules/sample": {"version": "1.0.0"}}}
    assert normalize_manifest(base, candidate, lock, {"prettier"}) == candidate
    lock["packages"]["node_modules/sample"]["version"] = "2.0.0"
    with pytest.raises(ValueError, match="policy review"):
        normalize_manifest(base, candidate, lock, {"prettier"})


def test_publisher_tool_version_must_match_source_pr(monkeypatch) -> None:
    original = {"devDependencies": {"prettier": "3.6.2"}}
    candidate = {"devDependencies": {"prettier": "3.9.6"}}
    source_lock = {
        "packages": {"": candidate, "node_modules/prettier": {"version": "3.9.6"}}
    }

    def api(path):
        if "ci/dependency-policy.toml" in path:
            content = b"[npm.build.prettier]\nrisk = 'low'\n"
        elif "package-lock.json" in path:
            content = json.dumps(source_lock).encode()
        else:
            content = json.dumps(
                original if path.endswith("a" * 40) else candidate
            ).encode()
        return {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(content).decode(),
        }

    monkeypatch.setattr("ci.publish_dependency_pr.api", api)
    data = payload()
    for filename, expected in (
        ("package.json", candidate),
        ("package-lock.json", source_lock),
    ):
        data["files"][0]["path"] = f"{FRONTEND}/{filename}"
        data["files"][0]["content"] = base64.b64encode(
            json.dumps(expected).encode()
        ).decode()
        verify_manifest_outputs("owner/repo", data)
        altered = json.loads(json.dumps(expected))
        if filename == "package.json":
            altered["devDependencies"]["prettier"] = "99.0.0"
        else:
            altered["packages"]["node_modules/prettier"]["version"] = "99.0.0"
        data["files"][0]["content"] = base64.b64encode(
            json.dumps(altered).encode()
        ).decode()
        with pytest.raises(ValueError, match="scripts or resolved"):
            verify_manifest_outputs("owner/repo", data)


def bot_signature(login="dependabot[bot]"):
    return {
        "oid": "b" * 40,
        "author": {"user": {"login": login}},
        "signature": {
            "isValid": True,
            "state": "VALID",
            "wasSignedByGitHub": True,
            "signer": {"login": "web-flow"},
        },
    }


@pytest.mark.parametrize("login", ["dependabot[bot]", "dep-prep[bot]"])
def test_github_signed_bot_provenance_accepted(monkeypatch, login):
    node = bot_signature(login)
    monkeypatch.setattr(
        "ci.publish_dependency_pr.api", lambda *a: {"data": {"nodes": [node]}}
    )
    verify_commit_provenance(
        [{"node_id": "node1", "sha": "b" * 40, "author": {"login": login}}], {login}
    )


@pytest.mark.parametrize(
    "alter",
    [
        "human_signature",
        "forged_signer",
        "invalid",
        "missing",
        "sha",
        "author",
        "error",
        "incomplete",
    ],
)
def test_bot_author_alone_cannot_authorize_publication(monkeypatch, alter):
    node = bot_signature()
    response = {"data": {"nodes": [node]}}
    if alter == "human_signature":
        node["signature"].update(wasSignedByGitHub=False, signer={"login": "attacker"})
    elif alter == "forged_signer":
        node["signature"]["signer"] = {"login": "attacker"}
    elif alter == "invalid":
        node["signature"]["isValid"] = False
    elif alter == "missing":
        node["signature"] = None
    elif alter == "sha":
        node["oid"] = "c" * 40
    elif alter == "author":
        node["author"]["user"]["login"] = "attacker"
    elif alter == "error":
        response["errors"] = [{"message": "unavailable"}]
    else:
        response["data"]["nodes"] = []
    monkeypatch.setattr("ci.publish_dependency_pr.api", lambda *a: response)
    with pytest.raises(ValueError, match="provenance"):
        verify_commit_provenance(
            [
                {
                    "node_id": "node1",
                    "sha": "b" * 40,
                    "author": {"login": "dependabot[bot]"},
                }
            ],
            {"dependabot[bot]"},
        )


@pytest.mark.parametrize(
    "spec",
    [
        "npm:other-package@1.0.0",
        "git+https://example.com/tool.git",
        "https://example.com/tool.tgz",
        "file:../../trusted",
        "workspace:*",
        "latest",
        "3.10.0-rc.1",
    ],
)
def test_tool_source_substitution_requires_review(spec):
    base = {"devDependencies": {"prettier": "3.6.2"}}
    candidate = {"devDependencies": {"prettier": spec}}
    with pytest.raises(ValueError, match="requires review"):
        normalize_manifest(base, candidate, {"packages": {}}, {"prettier"})


def registry_fixture():
    package = {"devDependencies": {"prettier": "3.9.6"}}
    lock = {
        "packages": {
            "": package,
            "node_modules/prettier": {
                "version": "3.9.6",
                "resolved": "https://registry.npmjs.org/prettier/-/prettier-3.9.6.tgz",
                "integrity": "sha512-YWJjZA==",
            },
        }
    }
    return package, lock


@pytest.mark.parametrize(
    "alter",
    [
        "host",
        "alias",
        "link",
        "missing_integrity",
        "tarball_identity",
        "credentials",
        "query",
    ],
)
def test_lockfile_source_substitution_requires_review(alter):
    package, lock = registry_fixture()
    validate_npm_sources(package, lock)
    entry = lock["packages"]["node_modules/prettier"]
    if alter == "host":
        entry["resolved"] = entry["resolved"].replace(
            "registry.npmjs.org", "evil.example"
        )
    elif alter == "alias":
        entry["name"] = "different-package"
    elif alter == "link":
        entry["link"] = True
    elif alter == "missing_integrity":
        del entry["integrity"]
    elif alter == "tarball_identity":
        entry["resolved"] = "https://registry.npmjs.org/other/-/other-3.9.6.tgz"
    elif alter == "credentials":
        entry["resolved"] = entry["resolved"].replace("https://", "https://attacker@")
    else:
        entry["resolved"] += "?redirect=evil"
    with pytest.raises(ValueError, match="requires review"):
        validate_npm_sources(package, lock)


def test_publisher_checks_source_even_without_manifest_artifact(monkeypatch):
    package, lock = registry_fixture()

    def api(path):
        value = lock if "package-lock.json" in path else package
        return {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(json.dumps(value).encode()).decode(),
        }

    monkeypatch.setattr("ci.publish_dependency_pr.api", api)
    pr = {"head": {"sha": "b" * 40}}
    verify_source_manifests("owner/repo", pr)
    lock["packages"]["node_modules/prettier"]["resolved"] = "file:../../trusted"
    with pytest.raises(ValueError, match="requires review"):
        verify_source_manifests("owner/repo", pr)
