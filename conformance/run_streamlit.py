"""Run the conformance gallery while retaining complete server output."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

root = Path(__file__).parents[1]
artifact_dir = root / "conformance-artifacts"
artifact_dir.mkdir(exist_ok=True)
command = [
    sys.executable,
    "-m",
    "streamlit",
    "run",
    str(root / "conformance" / "app" / "renderer_gallery.py"),
    "--server.headless=true",
    "--server.port=8513",
    "--browser.gatherUsageStats=false",
]
with (artifact_dir / "server.log").open("w", encoding="utf-8") as log:
    process = subprocess.Popen(
        command,
        cwd=artifact_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        log.write(line)
        log.flush()
raise SystemExit(process.wait())
