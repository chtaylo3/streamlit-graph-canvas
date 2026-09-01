"""Stage publishable files and evidence under an immutable release binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def stage(
    verified: Path,
    output: Path,
    *,
    repository: str,
    run_id: str,
    sha: str,
    tag: str,
    extra_evidence: tuple[Path, ...] = (),
) -> None:
    if output.exists():
        raise ValueError(f"refusing to replace release bundle: {output}")
    publish = output / "publish"
    evidence = output / "evidence"
    publish.mkdir(parents=True)
    evidence.mkdir()
    distributions = sorted([*verified.glob("*.whl"), *verified.glob("*.tar.gz")])
    if len(distributions) != 4:
        raise ValueError("release bundle requires two wheels and two sdists")
    for path in distributions:
        shutil.copy2(path, publish / path.name)
    for path in sorted(verified.glob("*.cdx.json")):
        shutil.copy2(path, evidence / path.name)
    for path in extra_evidence:
        if not path.is_file():
            raise ValueError(f"release evidence is missing: {path}")
        shutil.copy2(path, evidence / path.name)
    binding = {
        "repository": repository,
        "run_id": run_id,
        "sha": sha,
        "tag": tag,
    }
    (evidence / "release-binding.json").write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"{path.relative_to(output).as_posix()}\n"
            for path in files
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("verified", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    args = parser.parse_args()
    stage(
        args.verified,
        args.output,
        repository=args.repository,
        run_id=args.run_id,
        sha=args.sha,
        tag=args.tag,
        extra_evidence=tuple(args.evidence),
    )


if __name__ == "__main__":
    main()
