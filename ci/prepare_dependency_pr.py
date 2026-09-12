"""Prepare mechanical dependency changes without promoting support policy."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

FRONTEND = "packages/core/src/streamlit_graph_canvas/frontend"
INPUTS = {
    "uv.lock",
    f"{FRONTEND}/package.json",
    f"{FRONTEND}/package-lock.json",
    "tests/e2e/package.json",
    "tests/e2e/package-lock.json",
}
GENERATED = {
    "packages/core/THIRD_PARTY_LICENSES.md",
    f"{FRONTEND}/build/bundled-packages.json",
    f"{FRONTEND}/build/third-party-licenses.json",
}


def allowed_output(path: str) -> bool:
    return (
        path in INPUTS - {"uv.lock"}
        or path in GENERATED
        or bool(
            re.fullmatch(
                re.escape(FRONTEND) + r"/build/index-[A-Za-z0-9_-]+\.(js|css)", path
            )
        )
    )


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def manifest_declarations(
    base: dict, candidate: dict, tooling: set[str] | frozenset[str] = frozenset()
) -> dict:
    """Preserve runtime declarations and accept classified tool version updates."""
    result = json.loads(json.dumps(base))
    for group in ("dependencies", "devDependencies"):
        before, after = base.get(group, {}), candidate.get(group, {})
        if before.keys() != after.keys():
            raise ValueError("new or removed dependencies require policy review")
        if group == "devDependencies":
            for name in before.keys() & tooling:
                result[group][name] = after[name]
    excluded = {"dependencies", "devDependencies"}
    if {k: v for k, v in base.items() if k not in excluded} != {
        k: v for k, v in candidate.items() if k not in excluded
    }:
        raise ValueError("non-dependency manifest changes require review")
    return result


def normalize_manifest(
    base: dict,
    candidate: dict,
    lock: dict,
    tooling: set[str] | frozenset[str] = frozenset(),
) -> dict:
    """Retain runtime ranges while preserving candidate internal tool upgrades."""
    from packaging.version import Version

    result = manifest_declarations(base, candidate, tooling)
    for group in ("dependencies", "devDependencies"):
        for name, requirement in base.get(group, {}).items():
            if group == "devDependencies" and name in tooling:
                continue  # npm ci validates the candidate manifest and lockfile.
            version = lock["packages"]["node_modules/" + name]["version"]
            # The repository policy uses only exact and caret npm ranges.
            minimum = Version(requirement.lstrip("^"))
            current = Version(version)
            if requirement.startswith("^"):
                upper = (
                    Version(f"{minimum.major + 1}.0.0")
                    if minimum.major
                    else Version(f"0.{minimum.minor + 1}.0")
                    if minimum.minor
                    else Version(f"0.0.{minimum.micro + 1}")
                )
                compatible = minimum <= current < upper and not current.is_prerelease
            else:
                compatible = current == minimum
            if not compatible:
                raise ValueError(f"{name}@{version} requires explicit policy review")
    return result


def prepare(root: Path, base: str, head: str, output: Path) -> None:
    policy = tomllib.loads(
        git(root, "show", f"{base}:ci/dependency-policy.toml").decode()
    )
    changed = set(git(root, "diff", "--name-only", base, head).decode().splitlines())
    unknown = {p for p in changed if p not in INPUTS and not allowed_output(p)}
    if unknown:
        raise ValueError(f"requires maintainer review: {sorted(unknown)}")
    for directory in (FRONTEND, "tests/e2e"):
        if not any(p.startswith(directory + "/") for p in changed):
            continue
        manifest = root / directory / "package.json"
        lockfile = root / directory / "package-lock.json"
        original = json.loads(git(root, "show", f"{base}:{directory}/package.json"))
        lock = json.loads(lockfile.read_text())
        normalized = normalize_manifest(
            original,
            json.loads(manifest.read_text()),
            lock,
            set(policy["npm"]["build" if directory == FRONTEND else "test"]),
        )
        for group in ("dependencies", "devDependencies"):
            if group in normalized:
                lock["packages"][""][group] = normalized[group]
        manifest.write_text(json.dumps(normalized, indent=2) + "\n")
        lockfile.write_text(json.dumps(lock, indent=2) + "\n")
        subprocess.run(["npm", "ci"], cwd=root / directory, check=True)
    if any(p.startswith(FRONTEND + "/") for p in changed):
        subprocess.run(["npm", "run", "format:check"], cwd=root / FRONTEND, check=True)
        subprocess.run(["npm", "test"], cwd=root / FRONTEND, check=True)
        import sys

        generator = Path(__file__).with_name("generate_frontend_artifacts.py")
        subprocess.run(
            [sys.executable, str(generator), "--root", str(root), "--write"], check=True
        )
        subprocess.run(
            [sys.executable, str(generator), "--root", str(root), "--check"], check=True
        )
    paths = set(git(root, "diff", "--name-only", head).decode().splitlines())
    paths.update(
        git(root, "ls-files", "--others", "--exclude-standard").decode().splitlines()
    )
    files = []
    for name in sorted(paths):
        if not allowed_output(name):
            raise ValueError(f"unexpected preparation output: {name}")
        path = root / name
        if path.is_symlink():
            raise ValueError("symlink output is forbidden")
        content = path.read_bytes() if path.exists() else None
        files.append(
            {
                "path": name,
                "content": base64.b64encode(content).decode()
                if content is not None
                else None,
                "sha256": hashlib.sha256(content).hexdigest()
                if content is not None
                else None,
            }
        )
    output.write_text(
        json.dumps({"schema": 1, "base": base, "head": head, "files": files}) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not all(re.fullmatch(r"[a-f0-9]{40}", x) for x in (args.base, args.head)):
        raise SystemExit("expected immutable commit SHAs")
    if git(args.root, "rev-parse", "HEAD").decode().strip() != args.head:
        raise SystemExit("checkout differs from expected PR head")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    prepare(args.root, args.base, args.head, args.output)


if __name__ == "__main__":
    main()
