"""Validate preparation artifacts as data and commit through GitHub's API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tomllib
import urllib.parse
import zipfile
from pathlib import Path

from .prepare_dependency_pr import (
    FRONTEND,
    INPUTS,
    allowed_output,
    manifest_declarations,
    validate_npm_sources,
)

MAX_BYTES = 32 * 1024 * 1024


def api(path: str, body: dict | None = None) -> dict | list:
    command = ["gh", "api", path]
    if body is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def read_payload(archive: bytes) -> dict:
    if len(archive) > MAX_BYTES:
        raise ValueError("oversized archive")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        if len(entries) != 1 or entries[0].filename != "prepared.json":
            raise ValueError("artifact must contain only prepared.json")
        entry = entries[0]
        if entry.file_size > MAX_BYTES or stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError("unsafe artifact entry")
        payload = json.loads(zipped.read(entry))
    validate_payload(payload)
    return payload


def validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "base",
        "head",
        "files",
    }:
        raise ValueError("invalid payload schema")
    if payload["schema"] != 1 or not all(
        isinstance(payload[k], str) and re.fullmatch(r"[a-f0-9]{40}", payload[k])
        for k in ("base", "head")
    ):
        raise ValueError("invalid payload identity")
    if not isinstance(payload["files"], list) or len(payload["files"]) > 20:
        raise ValueError("invalid output count")
    seen = set()
    total = 0
    for item in payload["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "content", "sha256"}:
            raise ValueError("invalid file record")
        path = item["path"]
        if not isinstance(path, str) or path in seen or not allowed_output(path):
            raise ValueError("invalid output path")
        seen.add(path)
        if item["content"] is None:
            if "/build/index-" not in path or item["sha256"] is not None:
                raise ValueError("only obsolete bundles can be deleted")
            continue
        raw = base64.b64decode(item["content"], validate=True)
        total += len(raw)
        if total > MAX_BYTES or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("invalid output bytes")


def verify_commit_provenance(commits: list[dict], allowed: set[str]) -> None:
    """A claimed bot author must be backed by GitHub's own signing provenance."""
    result = api(
        "graphql",
        {
            "query": "query($ids: [ID!]!) { nodes(ids: $ids) { ... on Commit { "
            "oid author { user { login } } signature { isValid state "
            "wasSignedByGitHub signer { login } } } } }",
            "variables": {"ids": [c["node_id"] for c in commits]},
        },
    )
    if result.get("errors"):
        raise ValueError("could not establish bot commit provenance")
    nodes = result.get("data", {}).get("nodes", [])
    if len(nodes) != len(commits) or not commits:
        raise ValueError("incomplete bot commit provenance")
    for commit, node in zip(commits, nodes, strict=True):
        node = node or {}
        signature = node.get("signature") or {}
        author = (node.get("author") or {}).get("user") or {}
        signer = signature.get("signer") or {}
        if (
            node.get("oid") != commit["sha"]
            or author.get("login") != commit["author"]["login"]
            or author.get("login") not in allowed
            or signature.get("isValid") is not True
            or signature.get("state") != "VALID"
            or signature.get("wasSignedByGitHub") is not True
            or signer.get("login") not in allowed | {"web-flow"}
        ):
            raise ValueError(
                "PR contains a commit without trusted bot signing provenance"
            )


def verify_context(repo: str, run_id: int, attempt: int, bot: str) -> tuple[dict, dict]:
    run = api(f"repos/{repo}/actions/runs/{run_id}")
    workflow = api(f"repos/{repo}/actions/workflows/dependency-prepare.yml")
    if (
        run["event"] != "pull_request"
        or run["conclusion"] != "success"
        or run["run_attempt"] != attempt
        or run["workflow_id"] != workflow["id"]
        or run["head_repository"]["full_name"] != repo
    ):
        raise ValueError("untrusted preparation run")
    prs = run["pull_requests"]
    if len(prs) != 1:
        raise ValueError("expected one associated PR")
    pr = api(f"repos/{repo}/pulls/{prs[0]['number']}")
    if (
        pr["state"] != "open"
        or pr["user"]["login"] != "dependabot[bot]"
        or pr["base"]["ref"] != "main"
        or pr["head"]["repo"]["full_name"] != repo
        or pr["head"]["sha"] != run["head_sha"]
    ):
        raise ValueError("PR changed or is not eligible")
    if pr["commits"] > 100 or pr["changed_files"] > 100:
        raise ValueError("PR exceeds preparation limits")
    commits = api(f"repos/{repo}/pulls/{pr['number']}/commits?per_page=100")
    if len(commits) != pr["commits"]:
        raise ValueError("PR commit list changed or is incomplete")
    allowed = {"dependabot[bot]"} | ({bot} if bot else set())
    if any(
        not c.get("author")
        or c["author"]["login"] not in allowed
        or not c["commit"]["verification"]["verified"]
        for c in commits
    ):
        raise ValueError("PR contains unverified or unexpected authors")
    verify_commit_provenance(commits, allowed)
    files = api(f"repos/{repo}/pulls/{pr['number']}/files?per_page=100")
    if any(
        f["filename"] not in INPUTS and not allowed_output(f["filename"]) for f in files
    ):
        raise ValueError("PR changes trusted code or unsupported files")
    return run, pr


def verify_source_manifests(repo: str, pr: dict) -> None:
    """Validate source PR locks even when the artifact contains no manifest edits."""
    for directory in (FRONTEND, "tests/e2e"):
        files = []
        for name in ("package.json", "package-lock.json"):
            result = api(
                f"repos/{repo}/contents/{directory}/{name}?ref={pr['head']['sha']}"
            )
            if result.get("encoding") != "base64" or result.get("type") != "file":
                raise ValueError("expected ordinary source manifest")
            files.append(json.loads(base64.b64decode(result["content"])))
        validate_npm_sources(*files)


def commit_input(repo: str, pr: dict, payload: dict) -> dict:
    validate_payload(payload)
    if payload["head"] != pr["head"]["sha"] or payload["base"] != pr["base"]["sha"]:
        raise ValueError("stale preparation result")
    return {
        "branch": {"repositoryNameWithOwner": repo, "branchName": pr["head"]["ref"]},
        "expectedHeadOid": payload["head"],
        "message": {
            "headline": "Prepare dependency artifacts without promoting support"
        },
        "fileChanges": {
            "additions": [
                {"path": f["path"], "contents": f["content"]}
                for f in payload["files"]
                if f["content"] is not None
            ],
            "deletions": [
                {"path": f["path"]} for f in payload["files"] if f["content"] is None
            ],
        },
    }


def verify_manifest_outputs(repo: str, payload: dict) -> None:
    """A generated payload cannot introduce scripts or alter resolved packages."""
    for item in payload["files"]:
        path = item["path"]
        if not path.endswith(("/package.json", "/package-lock.json")):
            continue
        directory = path.rsplit("/", 1)[0]

        def read_file(name: str, sha: str) -> bytes:
            result = api(
                f"repos/{repo}/contents/{urllib.parse.quote(name, safe='/')}?ref={sha}"
            )
            if result.get("encoding") != "base64" or result.get("type") != "file":
                raise ValueError("expected ordinary GitHub file contents")
            return base64.b64decode(result["content"])

        def read_json(name: str, sha: str) -> dict:
            return json.loads(read_file(name, sha))

        original = read_json(directory + "/package.json", payload["base"])
        candidate = read_json(directory + "/package.json", payload["head"])
        policy = tomllib.loads(
            read_file("ci/dependency-policy.toml", payload["base"]).decode()
        )
        normalized = manifest_declarations(
            original,
            candidate,
            set(policy["npm"]["build" if directory == FRONTEND else "test"]),
        )
        actual = json.loads(base64.b64decode(item["content"], validate=True))
        if path.endswith("/package.json"):
            expected = normalized
        else:
            expected = read_json(path, payload["head"])
            for group in ("dependencies", "devDependencies"):
                if group in normalized:
                    expected["packages"][""][group] = normalized[group]
        if actual != expected:
            raise ValueError("preparation changed scripts or resolved dependencies")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    bot = os.environ.get("PREPARATION_BOT", "")
    _run, pr = verify_context(repo, args.run, args.attempt, bot)
    verify_source_manifests(repo, pr)
    artifacts = api(f"repos/{repo}/actions/runs/{args.run}/artifacts?per_page=100")[
        "artifacts"
    ]
    matches = [
        a for a in artifacts if a["name"] == f"dependency-preparation-{args.attempt}"
    ]
    if (
        len(matches) != 1
        or matches[0]["expired"]
        or matches[0]["size_in_bytes"] > MAX_BYTES
    ):
        raise ValueError("missing or invalid artifact")
    archive = subprocess.check_output(
        ["gh", "api", f"repos/{repo}/actions/artifacts/{matches[0]['id']}/zip"]
    )
    payload = read_payload(archive)
    mutation = commit_input(repo, pr, payload)
    verify_manifest_outputs(repo, payload)
    summary = (
        f"Dependency PR #{pr['number']}: {len(payload['files'])} "
        "prepared files; support endpoints unchanged.\n"
    )
    if args.commit and payload["files"]:
        # Compare again immediately before an atomic expected-head API write.
        _, current = verify_context(repo, args.run, args.attempt, bot)
        mutation = commit_input(repo, current, payload)
        result = api(
            "graphql",
            {
                "query": (
                    "mutation($input: CreateCommitOnBranchInput!) { "
                    "createCommitOnBranch(input: $input) { commit { url } } }"
                ),
                "variables": {"input": mutation},
            },
        )
        if result.get("errors"):
            raise ValueError(
                "GitHub rejected prepared commit: " + json.dumps(result["errors"])
            )
        summary += result["data"]["createCommitOnBranch"]["commit"]["url"] + "\n"
    else:
        summary += "Report-only or no changes; no commit created.\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(summary)


if __name__ == "__main__":
    main()
