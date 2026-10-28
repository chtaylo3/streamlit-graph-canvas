"""Run an e2e gallery while retaining complete server output.

The conformance gallery is the default. Feature suites select their gallery,
port, and log file through ``SGC_E2E_APP``, ``SGC_E2E_PORT``, and
``SGC_E2E_LOG`` so every suite gets the same server-log teardown checks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).parents[2]
e2e_dir = root / "tests" / "e2e"
artifact_dir = e2e_dir / "artifacts"
artifact_dir.mkdir(exist_ok=True)
app_name = Path(os.environ.get("SGC_E2E_APP", "renderer_gallery.py")).name
command = [
    sys.executable,
    "-m",
    "streamlit",
    "run",
    str(e2e_dir / "app" / app_name),
    "--server.headless=true",
    f"--server.port={int(os.environ.get('SGC_E2E_PORT', '8513'))}",
    "--browser.gatherUsageStats=false",
]
log_name = Path(os.environ.get("SGC_E2E_LOG", "server.log")).name
with (artifact_dir / log_name).open("w", encoding="utf-8") as log:
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
