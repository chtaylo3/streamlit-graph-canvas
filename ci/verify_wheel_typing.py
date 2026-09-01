"""Type-check a consumer against installed wheels, never workspace sources."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from .build_conformance_environment import wheel_for

CONSUMER = """\
from streamlit_graph_canvas import (
    EdgeType, EnabledRenderer, GraphData, GraphSchema, Node, NodeType,
    RendererKind, from_networkx, validate,
)

schema = GraphSchema(
    node_types={"service": NodeType("service")},
    edge_types={"calls": EdgeType("calls")},
)
graph = GraphData(nodes=(Node("api", "service", "API"),), edges=())
validate(schema, graph)
declaration: type[RendererKind] = RendererKind
enabled: type[EnabledRenderer] = EnabledRenderer
adapter = from_networkx
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheelhouse", type=Path)
    parser.add_argument("--constraints", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sgc-wheel-typing-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        subprocess.run(["uv", "venv", str(venv)], check=True)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = ["uv", "pip", "install", "--python", str(python)]
        if args.constraints:
            install.extend(["--constraints", str(args.constraints.resolve())])
        install.extend(
            [
                str(wheel_for(args.wheelhouse, "streamlit-graph-canvas")),
                str(wheel_for(args.wheelhouse, "streamlit-graph-canvas-contrib")),
                "mypy>=2.3.1",
            ]
        )
        subprocess.run(install, check=True)
        consumer = root / "consumer.py"
        consumer.write_text(CONSUMER, encoding="utf-8")
        subprocess.run(
            [str(python), "-m", "mypy", "--strict", str(consumer)], check=True
        )
        subprocess.run([str(python), str(consumer)], check=True)


if __name__ == "__main__":
    main()
