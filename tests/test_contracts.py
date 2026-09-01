from __future__ import annotations

import json
import shutil
from pathlib import Path

from ci.sync_contracts import synchronize

ROOT = Path(__file__).parents[1]


def test_generated_cross_language_contracts_are_current() -> None:
    assert synchronize(ROOT, write=False) == []


def test_contract_check_detects_authority_drift(tmp_path: Path) -> None:
    for relative in (
        "contracts/protocol.json",
        "packages/core/src/streamlit_graph_canvas/contract.py",
        "packages/core/src/streamlit_graph_canvas/frontend/src/contract.ts",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    source = tmp_path / "contracts/protocol.json"
    contract = json.loads(source.read_text(encoding="utf-8"))
    contract["codecVersion"] += 1
    source.write_text(json.dumps(contract), encoding="utf-8")
    assert set(synchronize(tmp_path, write=False)) == {
        "packages/core/src/streamlit_graph_canvas/contract.py",
        "packages/core/src/streamlit_graph_canvas/frontend/src/contract.ts",
    }


def test_contract_readme_mentions_every_authoritative_key() -> None:
    contract = json.loads(
        (ROOT / "contracts/protocol.json").read_text(encoding="utf-8")
    )
    documentation = (ROOT / "contracts/README.md").read_text(encoding="utf-8")
    expected = {*contract.keys(), *contract["limits"].keys()}
    missing = sorted(key for key in expected if f"`{key}`" not in documentation)
    assert missing == [], f"contract keys lack rationale: {missing}"
