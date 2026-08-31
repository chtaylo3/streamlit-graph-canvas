"""Create an isolated environment from the exact wheels selected by CI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


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
    missing = sorted({normalize(name) for name in contrib_projects} - declared)
    if missing:
        raise SystemExit(f"renderer distributions absent from every CI set: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", required=True, dest="set_name")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()

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
    subprocess.run(["uv", "venv", str(args.venv), "--python", "3.12"], check=True)
    wheels = [wheel_for(args.wheelhouse, "streamlit-graph-canvas")]
    wheels.extend(wheel_for(args.wheelhouse, name) for name in sets[args.set_name])
    python = args.venv / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), *map(str, wheels)],
        check=True,
    )
    subprocess.run(["uv", "pip", "check", "--python", str(python)], check=True)
    script = """
import importlib.metadata as md, json
names = %r
print(json.dumps({name: md.version(name) for name in names}, sort_keys=True))
""" % ["streamlit-graph-canvas", *sets[args.set_name]]
    inventory = subprocess.check_output([str(python), "-c", script], text=True)
    output = {
        "set": args.set_name,
        "packages": sets[args.set_name],
        "python": str(python),
        "inventory": json.loads(inventory),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
