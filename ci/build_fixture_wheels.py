"""Build the complete validated E2E fixture inventory exactly once."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from .fixture_inventory import FixtureProject, discover_fixture_projects

Runner = Callable[..., subprocess.CompletedProcess[str]]


def build_fixture_wheels(
    root: Path,
    out_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> tuple[FixtureProject, ...]:
    """Build each discovered fixture with an argument-array subprocess call."""

    repository = root.resolve()
    output = out_dir.resolve()
    fixtures = discover_fixture_projects(repository)
    for fixture in fixtures:
        if output == fixture.path or output.is_relative_to(fixture.path):
            raise ValueError(
                "fixture wheel output aliases source directory "
                f"{fixture.path}: {output}"
            )
    output.mkdir(parents=True, exist_ok=True)
    for fixture in fixtures:
        command: Sequence[str] = (
            "uv",
            "build",
            str(fixture.path),
            "--out-dir",
            str(output),
        )
        try:
            runner(command, cwd=repository, check=True, text=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"fixture build failed for {fixture.name!r} at {fixture.relative_path}"
            ) from error
    return fixtures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    fixtures = build_fixture_wheels(args.root, args.out_dir)
    print(f"built {len(fixtures)} fixture projects into {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
