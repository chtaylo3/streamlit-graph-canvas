"""Create an isolated environment from the exact wheels selected by CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from .fixture_inventory import discover_fixture_projects


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_sets(path: Path) -> dict[str, list[str]]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))["sets"]
    return {name: list(config["packages"]) for name, config in raw.items()}


def wheel_for(wheelhouse: Path, distribution: str) -> Path:
    prefix = normalize(distribution).replace("-", "_") + "-"
    matches = [
        path
        for path in wheelhouse.glob("*.whl")
        if path.name.lower().startswith(prefix)
    ]
    if len(matches) != 1:
        wheel_names = [path.name for path in matches]
        raise SystemExit(
            f"expected one wheel for {distribution!r}, found {wheel_names}"
        )
    return matches[0]


def validate_set_coverage(root: Path, sets: dict[str, list[str]]) -> None:
    declared = {
        normalize(package) for packages in sets.values() for package in packages
    }
    contrib_projects = []
    for project in (root / "packages").glob("*/pyproject.toml"):
        data = tomllib.loads(project.read_text(encoding="utf-8"))
        name = data["project"]["name"]
        if (
            name != "streamlit-graph-canvas"
            and "streamlit_graph_canvas.renderers"
            in data.get("project", {}).get("entry-points", {})
        ):
            contrib_projects.append(name)
    contrib_projects.extend(fixture.name for fixture in discover_fixture_projects(root))
    missing = sorted({normalize(name) for name in contrib_projects} - declared)
    if missing:
        raise SystemExit(f"local distributions absent from every CI set: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", required=True, dest="set_name")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--constraints", type=Path)
    parser.add_argument(
        "--dependency-lane", choices=("locked", "minimum", "latest"), default="locked"
    )
    parser.add_argument("--forward-scenario", choices=("streamlit", "pillow"))
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    if args.dependency_lane != "locked" and args.constraints is not None:
        raise SystemExit("minimum/latest lanes must resolve fresh without constraints")

    sets = load_sets(args.root / "ci" / "contrib-sets.toml")
    validate_set_coverage(args.root, sets)
    if args.set_name not in sets:
        raise SystemExit(
            f"unknown contrib set {args.set_name!r}; choose from {sorted(sets)}"
        )
    if args.venv.exists():
        if not args.venv.is_dir() or not (args.venv / "pyvenv.cfg").is_file():
            raise SystemExit(
                f"refusing to replace non-virtual-environment path: {args.venv}"
            )
        shutil.rmtree(args.venv)
    subprocess.run(["uv", "venv", str(args.venv), "--python", args.python], check=True)
    core_wheel = wheel_for(args.wheelhouse, "streamlit-graph-canvas")
    selected_wheels = [
        core_wheel,
        *(wheel_for(args.wheelhouse, name) for name in sets[args.set_name]),
    ]
    wheels: list[str | Path] = [
        f"streamlit-graph-canvas[atlas] @ {core_wheel.resolve().as_uri()}"
    ]
    wheels.extend(selected_wheels[1:])
    if args.dependency_lane != "locked":
        policy = tomllib.loads(
            (args.root / "ci/dependency-policy.toml").read_text(encoding="utf-8")
        )
        for name, entry in policy["python"].items():
            value = (
                f"=={entry['minimum']}"
                if args.dependency_lane == "minimum"
                else entry["supported"]
            )
            wheels.append(f"{name}{value}")
    python = args.venv / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    install = ["uv", "pip", "install", "--python", str(python)]
    if args.constraints is not None:
        install.extend(["--constraints", str(args.constraints.resolve())])
    install.extend(map(str, wheels))
    subprocess.run(install, check=True)
    if args.forward_scenario is not None:
        policy = tomllib.loads(
            (args.root / "ci/dependency-policy.toml").read_text(encoding="utf-8")
        )
        entry_name = "Pillow" if args.forward_scenario == "pillow" else "streamlit"
        subprocess.run(
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
                policy["python"][entry_name]["forward"],
            ],
            check=True,
        )
    subprocess.run(["uv", "pip", "check", "--python", str(python)], check=True)
    script = """
import importlib.metadata as md, json
names = %r
print(json.dumps({name: md.version(name) for name in names}, sort_keys=True))
""" % ["streamlit-graph-canvas", *sets[args.set_name]]
    inventory = subprocess.check_output([str(python), "-c", script], text=True)
    resolved = subprocess.check_output(
        ["uv", "pip", "freeze", "--python", str(python)], text=True
    ).splitlines()
    output = {
        "set": args.set_name,
        "dependency_lane": args.dependency_lane,
        "forward_scenario": args.forward_scenario,
        "packages": sets[args.set_name],
        "python": str(python),
        "python_version": subprocess.check_output(
            [str(python), "-c", "import platform; print(platform.python_version())"],
            text=True,
        ).strip(),
        "inventory": json.loads(inventory),
        "resolved": resolved,
        "wheels": {
            Path(path).name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in selected_wheels
        },
        "constraints_sha256": (
            hashlib.sha256(args.constraints.read_bytes()).hexdigest()
            if args.constraints is not None
            else None
        ),
    }
    rendered = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
