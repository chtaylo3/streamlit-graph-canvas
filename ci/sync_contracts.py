"""Generate and verify the small Python/TypeScript protocol authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "contracts/protocol.json"
PYTHON_TARGET = ROOT / "packages/core/src/streamlit_graph_canvas/contract.py"
TYPESCRIPT_TARGET = (
    ROOT / "packages/core/src/streamlit_graph_canvas/frontend/src/contract.ts"
)

FIELDS = (
    ("CONTRACT_SCHEMA_VERSION", "schemaVersion"),
    ("CODEC_VERSION", "codecVersion"),
    ("PROTOCOL_VERSION", "actionProtocolVersion"),
    ("RENDERER_API", "rendererApiVersion"),
    ("RENDERER_REGISTRY_SYMBOL", "rendererRegistrySymbol"),
    ("RENDERER_REGISTRATION_EVENT", "rendererRegistrationEvent"),
)
LIMITS = (
    ("MAX_ACTION_BATCH", "maxActionBatch"),
    ("MAX_SELECTION", "maxSelection"),
    ("MAX_IDENTIFIER_CHARS", "maxIdentifierChars"),
    ("MAX_BROWSER_STATE_BYTES", "maxBrowserStateBytes"),
    ("MAX_DATA_DEPTH", "maxDataDepth"),
    ("MAX_DATA_STRING_CHARS", "maxDataStringChars"),
    ("MAX_COLLECTION_ITEMS", "maxCollectionItems"),
    ("MAX_DATA_VALUES", "maxDataValues"),
    ("MAX_ATLAS_DIMENSION", "maxAtlasDimension"),
    ("MAX_ATLAS_DECODED_PIXELS", "maxAtlasDecodedPixels"),
    ("MAX_ATLAS_PAGE_BYTES", "maxAtlasPageBytes"),
    ("MAX_PRIMITIVE_COUNT", "maxPrimitiveCount"),
    ("MAX_PRIMITIVE_TEXT_CHARS", "maxPrimitiveTextChars"),
)


def _literal(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"contract values must be integers or strings: {value!r}")
    return json.dumps(value)


def render(contract: dict[str, Any]) -> tuple[str, str]:
    limits = contract.get("limits")
    if (
        set(contract) != {key for _, key in FIELDS} | {"limits"}
        or not isinstance(limits, dict)
        or set(limits) != {key for _, key in LIMITS}
    ):
        raise ValueError("contract fields differ from the supported authority schema")
    values = [(name, contract[key]) for name, key in FIELDS] + [
        (name, limits[key]) for name, key in LIMITS
    ]
    if any(isinstance(value, int) and value <= 0 for _, value in values):
        raise ValueError("numeric contract values must be positive")
    python = (
        '"""Generated cross-language protocol authority. Do not edit directly."""\n\n'
        + "\n".join(f"{name} = {_literal(value)}" for name, value in values)
        + "\n"
    )
    typescript = (
        "// Generated cross-language protocol authority. Do not edit directly.\n"
        + "\n".join(
            f"export const {name} = {_literal(value)} as const;"
            for name, value in values
        )
        + "\n"
    )
    return python, typescript


def synchronize(root: Path = ROOT, *, write: bool) -> list[str]:
    source = root / SOURCE.relative_to(ROOT)
    contract = json.loads(source.read_text(encoding="utf-8"))
    expected = render(contract)
    targets = (
        root / PYTHON_TARGET.relative_to(ROOT),
        root / TYPESCRIPT_TARGET.relative_to(ROOT),
    )
    stale: list[str] = []
    for target, content in zip(targets, expected, strict=True):
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            stale.append(str(target.relative_to(root)))
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
    return stale


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = synchronize(write=not args.check)
    if args.check and stale:
        raise SystemExit("generated protocol contracts are stale: " + ", ".join(stale))
    print("protocol contracts are synchronized")


if __name__ == "__main__":
    main()
