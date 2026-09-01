"""Read-only ESM syntax validation for packaged renderer bootstraps."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path

from .sync_renderer_assets import discover_renderer_javascript_assets

NODE_ESM_CHECK: tuple[str, ...] = ("node", "--input-type=module", "--check")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _parse(
    source: str,
    *,
    runner: Runner,
) -> subprocess.CompletedProcess[str]:
    return runner(
        NODE_ESM_CHECK,
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )


def verify_module_parser(*, runner: Runner = subprocess.run) -> None:
    """Prove the selected Node mode recognizes ESM and rejects invalid syntax."""

    valid = _parse("export const fixture = 1;\n", runner=runner)
    invalid = _parse("export const = ;\n", runner=runner)
    if valid.returncode != 0 or invalid.returncode == 0:
        raise RuntimeError(
            "Node renderer syntax probe failed: module mode must accept ESM exports "
            "and reject invalid ESM"
        )


def check_renderer_javascript(
    root: Path,
    *,
    runner: Runner = subprocess.run,
) -> tuple[Path, ...]:
    """Parse every declared bootstrap without changing any repository bytes."""

    verify_module_parser(runner=runner)
    assets = discover_renderer_javascript_assets(root)
    before = {asset: hashlib.sha256(asset.read_bytes()).hexdigest() for asset in assets}
    failures: list[str] = []
    for asset in assets:
        result = _parse(asset.read_text(encoding="utf-8"), runner=runner)
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout).strip()
            failures.append(f"{asset}: {diagnostic or 'Node syntax check failed'}")
    after = {asset: hashlib.sha256(asset.read_bytes()).hexdigest() for asset in assets}
    if before != after:
        changed = [str(asset) for asset in assets if before[asset] != after[asset]]
        raise RuntimeError(f"renderer syntax checker modified assets: {changed}")
    if failures:
        raise RuntimeError("renderer JavaScript syntax errors:\n" + "\n".join(failures))
    return assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    assets = check_renderer_javascript(args.root.resolve())
    print(f"renderer JavaScript syntax is valid for {len(assets)} assets")


if __name__ == "__main__":
    main()
