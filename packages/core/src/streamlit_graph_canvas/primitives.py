"""Closed, validated drawing vocabulary for Python badge renderers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .contract import MAX_PRIMITIVE_COUNT, MAX_PRIMITIVE_TEXT_CHARS
from .errors import Diagnostic, ValidationError


@dataclass(frozen=True, slots=True)
class RectPrim:
    x: float
    y: float
    width: float
    height: float
    fill: str
    radius: float = 0
    kind: Literal["rect"] = "rect"


@dataclass(frozen=True, slots=True)
class CirclePrim:
    cx: float
    cy: float
    radius: float
    fill: str
    kind: Literal["circle"] = "circle"


@dataclass(frozen=True, slots=True)
class TextPrim:
    x: float
    y: float
    text: str
    fill: str
    size: float = 11
    anchor: Literal["start", "middle", "end"] = "middle"
    kind: Literal["text"] = "text"


type Prim = RectPrim | CirclePrim | TextPrim


@dataclass(frozen=True, slots=True)
class BadgeContext:
    width: float
    height: float
    palette: frozenset[str]


def _invalid(code: str, message: str, subject: str | None = None) -> None:
    raise ValidationError(
        Diagnostic(
            code,
            message,
            "Correct the renderer output before enabling this renderer.",
            subject,
        )
    )


def _finite(*values: object) -> bool:
    return all(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        for value in values
    )


def validate_primitives(
    primitives: Sequence[Prim],
    context: BadgeContext,
    *,
    subject: str | None = None,
    max_primitives: int = MAX_PRIMITIVE_COUNT,
    max_text_length: int = MAX_PRIMITIVE_TEXT_CHARS,
) -> tuple[dict[str, Any], ...]:
    """Validate renderer output and return its JSON-compatible representation."""

    primitive_limit = min(max_primitives, MAX_PRIMITIVE_COUNT)
    text_limit = min(max_text_length, MAX_PRIMITIVE_TEXT_CHARS)
    if len(primitives) > primitive_limit:
        message = (
            f"Renderer emitted {len(primitives)} primitives; limit is "
            f"{primitive_limit}."
        )
        _invalid(
            "SGC_PRIMS_LIMIT",
            message,
            subject,
        )
    encoded: list[dict[str, Any]] = []
    for index, primitive in enumerate(primitives):
        item_subject = f"{subject or 'renderer'}#{index}"
        if type(primitive) not in (RectPrim, CirclePrim, TextPrim):
            _invalid(
                "SGC_PRIMS_TYPE",
                f"Unsupported primitive type {type(primitive).__name__!r}.",
                item_subject,
            )
        if isinstance(primitive, RectPrim):
            if primitive.kind != "rect":
                _invalid(
                    "SGC_PRIMS_TYPE",
                    "Rectangle primitive kind must be 'rect'.",
                    item_subject,
                )
            if (
                not _finite(
                    primitive.x,
                    primitive.y,
                    primitive.width,
                    primitive.height,
                    primitive.radius,
                )
                or min(primitive.width, primitive.height, primitive.radius) < 0
            ):
                _invalid(
                    "SGC_PRIMS_GEOMETRY",
                    "Rectangle geometry must be finite and non-negative.",
                    item_subject,
                )
            tone = primitive.fill
        elif isinstance(primitive, CirclePrim):
            if primitive.kind != "circle":
                _invalid(
                    "SGC_PRIMS_TYPE",
                    "Circle primitive kind must be 'circle'.",
                    item_subject,
                )
            if (
                not _finite(primitive.cx, primitive.cy, primitive.radius)
                or primitive.radius < 0
            ):
                _invalid(
                    "SGC_PRIMS_GEOMETRY",
                    "Circle geometry must be finite and non-negative.",
                    item_subject,
                )
            tone = primitive.fill
        else:
            if primitive.kind != "text" or primitive.anchor not in {
                "start",
                "middle",
                "end",
            }:
                _invalid(
                    "SGC_PRIMS_TYPE",
                    "Text primitive kind and anchor are invalid.",
                    item_subject,
                )
            if (
                not _finite(primitive.x, primitive.y, primitive.size)
                or primitive.size <= 0
            ):
                _invalid(
                    "SGC_PRIMS_GEOMETRY",
                    "Text geometry must be finite and its size must be positive.",
                    item_subject,
                )
            if not isinstance(primitive.text, str):
                _invalid(
                    "SGC_PRIMS_TYPE",
                    "Text primitive content must be a string.",
                    item_subject,
                )
            if len(primitive.text) > text_limit:
                _invalid(
                    "SGC_PRIMS_TEXT_LIMIT",
                    f"Text exceeds the {text_limit}-character limit.",
                    item_subject,
                )
            tone = primitive.fill
        if not isinstance(tone, str):
            _invalid(
                "SGC_PRIMS_TYPE",
                "Primitive fill must be a symbolic palette string.",
                item_subject,
            )
        if tone not in context.palette:
            _invalid(
                "SGC_PRIMS_TONE",
                f"Primitive references undeclared palette tone {tone!r}.",
                item_subject,
            )
        encoded.append(asdict(primitive))
    return tuple(encoded)
