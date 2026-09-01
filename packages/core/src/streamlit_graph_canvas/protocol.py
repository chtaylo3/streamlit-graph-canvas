"""Validated browser-to-Python canvas state and action protocol."""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, NoReturn

from .contract import (
    MAX_ACTION_BATCH,
    MAX_BROWSER_STATE_BYTES,
    MAX_IDENTIFIER_CHARS,
    MAX_SELECTION,
    PROTOCOL_VERSION,
)
from .errors import Diagnostic, ValidationError
from .json_budget import JsonLimitError, bounded_json_size
from .model import GraphData

MAX_ACTION_SEQUENCE = 2**53 - 1


@dataclass(frozen=True, slots=True)
class CanvasViewport:
    x: float
    y: float
    zoom: float


@dataclass(frozen=True, slots=True)
class ActionModifiers:
    shift: bool
    meta: bool
    alt: bool


@dataclass(frozen=True, slots=True)
class CanvasAction:
    seq: int
    operation_id: str
    gesture: str
    node_id: str
    node_type: str
    topology_revision: int
    modifiers: ActionModifiers


def _fail(code: str, message: str, action: str) -> NoReturn:
    raise ValidationError(Diagnostic(code, message, action))


def parse_selection(value: Any, graph: GraphData) -> tuple[str, ...]:
    """Validate persistent selection and reconcile removed nodes."""

    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        _fail(
            "SGC_STATE_SELECTION",
            "Browser selection state must be a list of node IDs.",
            "Discard the malformed component state and remount the canvas.",
        )
    if len(value) > MAX_SELECTION:
        _fail(
            "SGC_STATE_SELECTION_LIMIT",
            f"Browser selection exceeds the {MAX_SELECTION}-node limit.",
            "Discard the oversized component state and remount the canvas.",
        )
    if not all(
        isinstance(item, str) and 0 < len(item) <= MAX_IDENTIFIER_CHARS
        for item in value
    ):
        _fail(
            "SGC_STATE_SELECTION",
            "Browser selection node IDs must be bounded non-empty strings.",
            "Discard the malformed component state and remount the canvas.",
        )
    try:
        bounded_json_size(
            value,
            max_bytes=MAX_BROWSER_STATE_BYTES,
            max_depth=2,
            max_string_chars=MAX_IDENTIFIER_CHARS,
            max_collection_items=MAX_SELECTION,
            max_values=MAX_SELECTION + 1,
        )
    except JsonLimitError as error:
        _fail(
            "SGC_STATE_SELECTION_LIMIT",
            f"Browser selection is outside the bounded envelope: {error.detail}.",
            "Discard the oversized component state and remount the canvas.",
        )
    existing = {node.id for node in graph.nodes}
    return tuple(dict.fromkeys(item for item in value if item in existing))


def parse_viewport(value: Any) -> CanvasViewport | None:
    """Validate a persistent React Flow viewport."""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"x", "y", "zoom"}:
        _fail(
            "SGC_STATE_VIEWPORT",
            "Browser viewport state must contain only x, y, and zoom.",
            "Discard the malformed component state and remount the canvas.",
        )
    coordinates: list[float] = []
    for name in ("x", "y", "zoom"):
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            _fail(
                "SGC_STATE_VIEWPORT",
                f"Viewport {name} must be a finite number.",
                "Discard the malformed component state and remount the canvas.",
            )
        coordinate = float(raw)
        if not math.isfinite(coordinate):
            _fail(
                "SGC_STATE_VIEWPORT",
                f"Viewport {name} must be a finite number.",
                "Discard the malformed component state and remount the canvas.",
            )
        coordinates.append(coordinate)
    if not 0.08 <= coordinates[2] <= 2.5:
        _fail(
            "SGC_STATE_VIEWPORT_ZOOM",
            "Viewport zoom is outside the supported range 0.08 through 2.5.",
            "Clamp the browser viewport to the configured zoom range.",
        )
    return CanvasViewport(*coordinates)


def _mapping(value: Any, *, subject: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            "SGC_ACTION_SHAPE",
            f"{subject} must be an object.",
            "Discard the malformed browser action and remount the canvas.",
        )
    return value


def _parse_action(value: Any) -> CanvasAction:
    raw = _mapping(value, subject="Browser action")
    expected = {
        "protocolVersion",
        "seq",
        "operationId",
        "gesture",
        "nodeId",
        "nodeType",
        "topologyRevision",
        "target",
        "modifiers",
    }
    if set(raw) != expected:
        _fail(
            "SGC_ACTION_SHAPE",
            "Browser action fields do not match the v1 click protocol.",
            "Use the documented v1 action envelope.",
        )
    if raw["protocolVersion"] != PROTOCOL_VERSION:
        _fail(
            "SGC_ACTION_PROTOCOL",
            f"Unsupported browser action protocol {raw['protocolVersion']!r}.",
            f"Send protocol version {PROTOCOL_VERSION}.",
        )
    seq = raw["seq"]
    revision = raw["topologyRevision"]
    if (
        isinstance(seq, bool)
        or not isinstance(seq, int)
        or not 1 <= seq <= MAX_ACTION_SEQUENCE
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
    ):
        _fail(
            "SGC_ACTION_SEQUENCE",
            "Action sequence and topology revision must be positive safe integers.",
            "Reset the browser action queue from the acknowledged sequence.",
        )
    operation_id = raw["operationId"]
    try:
        parsed_operation_id = str(uuid.UUID(operation_id))
    except (AttributeError, TypeError, ValueError):
        _fail(
            "SGC_ACTION_OPERATION_ID",
            "Action operationId must be a canonical UUID.",
            "Generate operation IDs with crypto.randomUUID().",
        )
    if parsed_operation_id != operation_id:
        _fail(
            "SGC_ACTION_OPERATION_ID",
            "Action operationId must be a canonical lowercase UUID.",
            "Generate operation IDs with crypto.randomUUID().",
        )
    if raw["gesture"] != "click" or raw["target"] != {"kind": "node"}:
        _fail(
            "SGC_ACTION_GESTURE",
            "Protocol v1 supports only a click gesture targeting a node.",
            "Use the v1 click envelope or wait for a later protocol version.",
        )
    if not all(
        isinstance(raw[name], str) and 0 < len(raw[name]) <= MAX_IDENTIFIER_CHARS
        for name in ("nodeId", "nodeType")
    ):
        _fail(
            "SGC_ACTION_NODE",
            "Action nodeId and nodeType must be bounded non-empty strings.",
            "Use identifiers from the current authoritative topology.",
        )
    modifiers = _mapping(raw["modifiers"], subject="Action modifiers")
    if set(modifiers) != {"shift", "meta", "alt"} or not all(
        isinstance(modifiers[name], bool) for name in modifiers
    ):
        _fail(
            "SGC_ACTION_MODIFIERS",
            "Action modifiers must contain boolean shift, meta, and alt values.",
            "Send the documented modifier object.",
        )
    return CanvasAction(
        seq=seq,
        operation_id=operation_id,
        gesture="click",
        node_id=raw["nodeId"],
        node_type=raw["nodeType"],
        topology_revision=revision,
        modifiers=ActionModifiers(
            shift=modifiers["shift"],
            meta=modifiers["meta"],
            alt=modifiers["alt"],
        ),
    )


def parse_actions(
    value: Any,
    graph: GraphData,
    *,
    topology_revision: int,
    acknowledged_sequence: int,
) -> tuple[tuple[CanvasAction, ...], int]:
    """Validate, deduplicate, and reconcile an ordered browser action batch."""

    if value is None:
        return (), acknowledged_sequence
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(
            "SGC_ACTION_BATCH",
            "Browser actions must be an ordered list.",
            "Send an ordered list of v1 action envelopes.",
        )
    if len(value) > MAX_ACTION_BATCH:
        _fail(
            "SGC_ACTION_BATCH_LIMIT",
            f"Browser action batch exceeds the {MAX_ACTION_BATCH}-action limit.",
            "Wait for acknowledgement before sending more actions.",
        )
    try:
        bounded_json_size(
            value,
            max_bytes=MAX_BROWSER_STATE_BYTES,
            max_depth=8,
            max_string_chars=MAX_IDENTIFIER_CHARS,
            max_collection_items=MAX_ACTION_BATCH,
            max_values=MAX_ACTION_BATCH * 16,
        )
    except JsonLimitError as error:
        _fail(
            "SGC_ACTION_BYTES_LIMIT",
            f"Browser action batch is outside the bounded envelope: {error.detail}.",
            "Discard the oversized action queue and remount the canvas.",
        )
    parsed = tuple(_parse_action(item) for item in value)
    if any(left.seq >= right.seq for left, right in pairwise(parsed)):
        _fail(
            "SGC_ACTION_ORDER",
            "Browser actions must have strictly increasing sequence numbers.",
            "Sort and deduplicate the action queue before sending it.",
        )
    nodes = {node.id: node.type for node in graph.nodes}
    accepted = tuple(
        action
        for action in parsed
        if action.seq > acknowledged_sequence
        and action.topology_revision == topology_revision
        and nodes.get(action.node_id) == action.node_type
    )
    acknowledged = max(
        (action.seq for action in parsed if action.seq > acknowledged_sequence),
        default=acknowledged_sequence,
    )
    return accepted, acknowledged
