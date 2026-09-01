"""Verify immutable tag, protected-main ancestry, and exact-SHA workflow success."""

from __future__ import annotations

import argparse
import json
import os
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _api(repository: str, path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _tag_commit(repository: str, tag: str, token: str) -> str:
    reference = _api(
        repository,
        "git/ref/tags/" + urllib.parse.quote(tag, safe=""),
        token,
    )["object"]
    while reference["type"] == "tag":
        reference = _api(repository, f"git/tags/{reference['sha']}", token)["object"]
    if reference["type"] != "commit":
        raise RuntimeError("release tag does not resolve to a commit")
    return str(reference["sha"])


def verify(
    repository: str,
    sha: str,
    tag: str,
    token: str,
    workflows: list[str],
    *,
    attempts: int = 40,
    interval: int = 30,
) -> dict[str, Any]:
    tag_sha = _tag_commit(repository, tag, token)
    if tag_sha != sha:
        raise RuntimeError(f"tag resolves to {tag_sha}, not workflow SHA {sha}")
    comparison = _api(repository, f"compare/{sha}...main", token)
    if comparison.get("merge_base_commit", {}).get("sha") != sha:
        raise RuntimeError("release SHA is not an ancestor of protected main")
    evidence: dict[str, Any] = {}
    for attempt in range(attempts):
        evidence = {}
        incomplete = []
        for workflow in workflows:
            query = urllib.parse.urlencode(
                {"head_sha": sha, "status": "completed", "per_page": 100}
            )
            runs = _api(
                repository,
                f"actions/workflows/{workflow}/runs?{query}",
                token,
            ).get("workflow_runs", [])
            successful = [
                run
                for run in runs
                if run.get("head_sha") == sha and run.get("conclusion") == "success"
            ]
            if not successful:
                incomplete.append(workflow)
                continue
            run = max(successful, key=lambda item: item["id"])
            evidence[workflow] = {
                "run_id": run["id"],
                "event": run["event"],
                "conclusion": run["conclusion"],
                "head_sha": run["head_sha"],
            }
        if not incomplete:
            return {
                "repository": repository,
                "sha": sha,
                "tag": tag,
                "tag_sha": tag_sha,
                "main_merge_base": comparison["merge_base_commit"]["sha"],
                "workflows": evidence,
            }
        if attempt + 1 < attempts:
            time.sleep(interval)
    raise RuntimeError(f"required exact-SHA workflows did not succeed: {incomplete}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = tomllib.loads(
        (args.root / "ci/dependency-policy.toml").read_text(encoding="utf-8")
    )
    result = verify(
        os.environ["GITHUB_REPOSITORY"],
        os.environ["GITHUB_SHA"],
        os.environ["GITHUB_REF_NAME"],
        os.environ["GITHUB_TOKEN"],
        policy["ci"]["release_required_workflows"],
    )
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
