"""Closed, validated drawing vocabulary for Python badge renderers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

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


def _finite(*values: float) -> bool:
    return all(math.isfinite(value) for value in values)


def validate_primitives(
    primitives: Sequence[Prim],
    context: BadgeContext,
    *,
    subject: str | None = None,
    max_primitives: int = 200,
    max_text_length: int = 1024,
) -> tuple[dict[str, Any], ...]:
    """Validate renderer output and return its JSON-compatible representation."""

    if len(primitives) > max_primitives:
        message = (
            f"Renderer emitted {len(primitives)} primitives; limit is {max_primitives}."
        )
        _invalid(
            "SGC_PRIMS_LIMIT",
            message,
            subject,
        )
    encoded: list[dict[str, Any]] = []
    for index, primitive in enumerate(primitives):
        item_subject = f"{subject or 'renderer'}#{index}"
        if not isinstance(primitive, (RectPrim, CirclePrim, TextPrim)):
            _invalid(
                "SGC_PRIMS_TYPE",
                f"Unsupported primitive type {type(primitive).__name__!r}.",
                item_subject,
            )
        if isinstance(primitive, RectPrim):
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
            if (
                not _finite(primitive.x, primitive.y, primitive.size)
                or primitive.size <= 0
            ):
                _invalid(
                    "SGC_PRIMS_GEOMETRY",
                    "Text geometry must be finite and its size must be positive.",
                    item_subject,
                )
            if len(primitive.text) > max_text_length:
                _invalid(
                    "SGC_PRIMS_TEXT_LIMIT",
                    f"Text exceeds the {max_text_length}-character limit.",
                    item_subject,
                )
            tone = primitive.fill
        if tone not in context.palette:
            _invalid(
                "SGC_PRIMS_TONE",
                f"Primitive references undeclared palette tone {tone!r}.",
                item_subject,
            )
        encoded.append(asdict(primitive))
    return tuple(encoded)
