"""Generate the human-readable compatibility matrix from dependency policy."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any


def render(policy: dict[str, Any]) -> bytes:
    lines = [
        "# Generated dependency compatibility matrix",
        "",
        "This file is generated from `ci/dependency-policy.toml` by",
        "`ci/generate_dependency_docs.py`. Do not edit it manually.",
        "",
        "## Toolchains",
        "",
        "| Surface | Minimum/locked | Forward signal |",
        "| --- | --- | --- |",
        (
            f"| Python | {policy['toolchains']['python_min']} "
            f"({', '.join(policy['toolchains']['python_locked'])}) | "
            f"{policy['toolchains']['python_forward']} |"
        ),
        (
            f"| Node.js | {policy['toolchains']['node_supported']} "
            f"(locked {policy['toolchains']['node_locked']}) | "
            f"{policy['toolchains']['node_forward']} |"
        ),
        "",
        "## Python runtime",
        "",
        "| Dependency | Minimum | Supported | Forward | Risk |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, entry in policy["python"].items():
        lines.append(
            f"| {name} | {entry['minimum']} | `{entry['supported']}` | "
            f"`{entry.get('forward', '—')}` | {entry['risk']} |"
        )
    lines.extend(
        [
            "",
            "## Browser and build dependencies",
            "",
            (
                "| Group | Dependency | Minimum | Supported | Forward | "
                "Coupled with | Risk |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for group, entries in policy["npm"].items():
        for name, entry in entries.items():
            lines.append(
                f"| {group} | {name} | {entry['minimum']} | "
                f"`{entry['supported']}` | `{entry.get('forward', '—')}` | "
                f"{entry.get('coupling', '—')} | {entry['risk']} |"
            )
    lines.extend(
        [
            "",
            "## CI signals",
            "",
            f"Blocking: {', '.join(policy['ci']['blocking_lanes'])}.",
            "",
            f"Advisory: {', '.join(policy['ci']['advisory_lanes'])}.",
            "",
        ]
    )
    return "\n".join(lines).encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    policy = tomllib.loads(
        (args.root / "ci/dependency-policy.toml").read_text(encoding="utf-8")
    )
    content = render(policy)
    output = args.root / "docs/dependency-compatibility.generated.md"
    if args.check:
        if not output.is_file() or output.read_bytes() != content:
            raise SystemExit(
                "generated dependency compatibility documentation is stale"
            )
    else:
        output.write_bytes(content)
    print("dependency compatibility documentation is synchronized")


if __name__ == "__main__":
    main()
