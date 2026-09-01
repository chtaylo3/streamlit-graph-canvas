"""Create reproducible minimum/latest/forward compatibility environments."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any

if __package__:
    from .generate_frontend_licenses import generate
else:
    from generate_frontend_licenses import generate


def load_policy(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / "ci/dependency-policy.toml").read_text())


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def pillow_runtime_probe(python: Path) -> dict[str, str | int]:
    """Exercise the installed guard and record the cache identity in CI evidence."""

    script = (
        "import json, PIL; "
        "from streamlit_graph_canvas.atlas import pillow_rasterizer_version; "
        "print(json.dumps({'pillow': PIL.__version__, "
        "'atlas_rasterizer': pillow_rasterizer_version(subject='CI probe')}))"
    )
    result = subprocess.run(
        [str(python), "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        return {
            "status": "rejected",
            "exit_code": result.returncode,
            "diagnostic": result.stdout[-4000:],
        }
    return {"status": "accepted", **json.loads(result.stdout)}


def python_specs(policy: dict[str, Any], lane: str, scenario: str = "all") -> list[str]:
    specs = []
    for name, entry in policy["python"].items():
        if lane == "minimum":
            specs.append(f"{name}=={entry['minimum']}")
        elif lane == "latest":
            specs.append(f"{name}{entry['supported']}")
        elif "forward" in entry and scenario in {"all", name.casefold()}:
            specs.append(entry["forward"])
    return specs


def python_lane(args: argparse.Namespace, policy: dict[str, Any]) -> None:
    root, venv = args.root, args.venv.resolve()
    if venv.exists():
        if not venv.is_dir() or not (venv / "pyvenv.cfg").is_file():
            raise SystemExit(
                f"refusing to replace non-virtual-environment path: {venv}"
            )
        shutil.rmtree(venv)
    run(["uv", "venv", str(venv), "--python", args.python])
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command = [
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--prerelease",
        "allow" if args.lane == "forward" else "if-necessary",
        str(root / "packages/core") + "[atlas,networkx]",
        str(root / "packages/contrib"),
        "pytest",
        "hypothesis>=6.0.0",
        *python_specs(policy, args.lane if args.lane != "forward" else "latest"),
    ]
    run(command)
    if args.lane == "forward":
        forward = python_specs(policy, "forward", args.scenario)
        if forward:
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--prerelease",
                    "allow",
                    "--upgrade",
                    "--no-deps",
                    *forward,
                ]
            )
    else:
        run(["uv", "pip", "check", "--python", str(python)])
    tests = subprocess.run(
        [str(python), "-m", "pytest", "packages/core/tests", "packages/contrib/tests"],
        cwd=root,
        check=False,
    )
    inventory = subprocess.check_output(
        ["uv", "pip", "freeze", "--python", str(python)], text=True
    ).splitlines()
    runtime = pillow_runtime_probe(python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "lane": args.lane,
                "python": args.python,
                "packages": inventory,
                "runtime": runtime,
            },
            indent=2,
        )
        + "\n"
    )
    if tests.returncode:
        raise SystemExit(
            f"compatibility tests failed with exit code {tests.returncode}"
        )
    if runtime["status"] != "accepted":
        raise SystemExit("Pillow runtime guard rejected the compatibility environment")


def npm_specs(policy: dict[str, Any], lane: str, scenario: str) -> list[str]:
    groups = policy["npm"]
    entries = {**groups["runtime"], **groups["build"]}
    if scenario == "react-flow":
        names = {
            "react",
            "react-dom",
            "@types/react",
            "@types/react-dom",
            "@xyflow/react",
        }
    elif scenario == "elk":
        names = {"elkjs"}
    elif scenario == "component":
        names = {"@streamlit/component-v2-lib"}
    else:
        names = set(entries)
    specs = []
    for name in sorted(names):
        entry = entries[name]
        if lane == "minimum":
            value = entry["minimum"]
        elif lane == "latest":
            value = entry["supported"]
        else:
            value = entry.get("forward", entry["supported"])
        specs.append(f"{name}@{value}")
    return specs


def frontend_lane(args: argparse.Namespace, policy: dict[str, Any]) -> None:
    directory = args.root / "packages/core/src/streamlit_graph_canvas/frontend"
    with tempfile.TemporaryDirectory(prefix="sgc-frontend-") as temporary:
        workspace = Path(temporary) / "frontend"
        shutil.copytree(
            directory,
            workspace,
            ignore=shutil.ignore_patterns("node_modules", "build"),
        )
        package_path = workspace / "package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        (workspace / "package-lock.json").unlink(missing_ok=True)
        selected = {
            spec.rsplit("@", 1)[0]: spec.rsplit("@", 1)[1]
            for spec in npm_specs(policy, args.lane, args.scenario)
        }
        for group in ("dependencies", "devDependencies"):
            for name in package.get(group, {}):
                if name in selected:
                    package[group][name] = selected[name]
        package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
        run(["npm", "install", "--legacy-peer-deps"], cwd=workspace)
        inventory_result = subprocess.run(
            ["npm", "ls", "--all", "--json"],
            cwd=workspace,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if inventory_result.returncode and args.lane != "forward":
            raise SystemExit(
                "resolved frontend dependency tree is invalid:\n"
                + inventory_result.stdout
            )
        run(["npm", "test"], cwd=workspace)
        run(["npm", "run", "build"], cwd=workspace)
        license_document, license_inventory = generate(args.root, frontend=workspace)
        (workspace / "build/third-party-licenses.json").write_bytes(license_inventory)
        staged_package: str | None = None
        if args.output_tree is not None:
            output_tree = args.output_tree.resolve()
            if output_tree.exists():
                if any(output_tree.iterdir()):
                    raise SystemExit(
                        f"refusing to replace non-empty output tree: {output_tree}"
                    )
                output_tree.rmdir()
            shutil.copytree(args.root / "packages/core", output_tree)
            output_build = output_tree / "src/streamlit_graph_canvas/frontend/build"
            if output_build.exists():
                shutil.rmtree(output_build)
            shutil.copytree(workspace / "build", output_build)
            (output_tree / "THIRD_PARTY_LICENSES.md").write_bytes(license_document)
            staged_package = str(output_tree)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "lane": args.lane,
                    "scenario": args.scenario,
                    "requested": selected,
                    "npm_ls_exit_code": inventory_result.returncode,
                    "npm_ls": inventory_result.stdout,
                    "staged_package": staged_package,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    subparsers = parser.add_subparsers(dest="command", required=True)
    py = subparsers.add_parser("python")
    py.add_argument("--lane", choices=("minimum", "latest", "forward"), required=True)
    py.add_argument("--python", required=True)
    py.add_argument(
        "--scenario",
        choices=("all", "supported", "streamlit", "pillow", "networkx"),
        default="all",
    )
    py.add_argument("--venv", type=Path, required=True)
    py.add_argument("--output", type=Path, required=True)
    frontend = subparsers.add_parser("frontend")
    frontend.add_argument(
        "--lane", choices=("minimum", "latest", "forward"), required=True
    )
    frontend.add_argument(
        "--scenario", choices=("all", "react-flow", "elk", "component"), default="all"
    )
    frontend.add_argument("--output", type=Path, required=True)
    frontend.add_argument(
        "--output-tree",
        type=Path,
        help=(
            "materialize an explicit staged core package without changing the checkout"
        ),
    )
    args = parser.parse_args()
    policy = load_policy(args.root)
    if args.command == "python":
        python_lane(args, policy)
    else:
        frontend_lane(args, policy)


if __name__ == "__main__":
    main()
