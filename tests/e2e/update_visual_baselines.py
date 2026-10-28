"""Run the visual snapshot suite inside the pinned Playwright Linux image.

Baselines must come from the same image CI uses, because fonts render
differently on each OS. The image tag follows the locked ``@playwright/test``
version, so a Playwright upgrade also moves the image.

    python tests/e2e/update_visual_baselines.py           # rewrite baselines
    python tests/e2e/update_visual_baselines.py --check   # compare only

The workspace is bind-mounted, but the Python environment and node_modules
stay inside the container so host checkouts keep their own platform builds.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

root = Path(__file__).parents[2]
lock = json.loads((root / "tests/e2e/package-lock.json").read_text(encoding="utf-8"))
version = lock["packages"]["node_modules/@playwright/test"]["version"]
image = f"mcr.microsoft.com/playwright:v{version}-noble"

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--check", action="store_true", help="compare without updating")
args = parser.parse_args()
update = "" if args.check else " --update-snapshots=changed"
script = (
    "set -euo pipefail\n"
    "curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null\n"
    "export PATH=$HOME/.local/bin:$PATH\n"
    "uv sync --locked --quiet\n"
    "cd tests/e2e && npm ci --silent\n"
    f"npx playwright test --config playwright.visual.config.ts{update}\n"
)
raise SystemExit(
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--ipc=host",
            "-v",
            f"{root}:/repo",
            "-v",
            "/repo/tests/e2e/node_modules",
            "-e",
            "UV_PROJECT_ENVIRONMENT=/opt/sgc-venv",
            "-e",
            "SGC_CONFORMANCE_PYTHON=/opt/sgc-venv/bin/python",
            "-w",
            "/repo",
            image,
            "bash",
            "-c",
            script,
        ],
        check=False,
    ).returncode
)
