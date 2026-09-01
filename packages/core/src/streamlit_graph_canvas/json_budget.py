"""Single-pass JSON validation with exact compact UTF-8 byte accounting."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


class JsonLimitError(ValueError):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


@dataclass(slots=True)
class JsonBudget:
    max_bytes: int
    max_depth: int
    max_string_chars: int
    max_collection_items: int
    max_values: int
    used: int = 0
    values: int = 0

    def token(self, value: str) -> None:
        self.used += len(value.encode("utf-8"))
        if self.used > self.max_bytes:
            raise JsonLimitError("size", f"JSON exceeds {self.max_bytes} bytes")

    def _value(self) -> None:
        self.values += 1
        if self.values > self.max_values:
            raise JsonLimitError("values", f"JSON exceeds {self.max_values} values")

    def scalar(self, value: bool | int | float | str | None) -> None:
        self._value()
        if isinstance(value, str) and len(value) > self.max_string_chars:
            raise JsonLimitError(
                "string", f"string exceeds {self.max_string_chars} characters"
            )
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and not -(2**53 - 1) <= value <= 2**53 - 1
        ):
            raise JsonLimitError("integer", "integer is outside the safe range")
        if isinstance(value, float) and not math.isfinite(value):
            raise JsonLimitError("number", "number is not finite")
        self.token(json.dumps(value, allow_nan=False, separators=(",", ":")))

    def object_fields(
        self, fields: Iterable[tuple[str, Any]], *, depth: int = 0
    ) -> None:
        if depth > self.max_depth:
            raise JsonLimitError("depth", f"JSON exceeds depth {self.max_depth}")
        self._value()
        self.token("{")
        for count, (key, value) in enumerate(fields, start=1):
            if count > self.max_collection_items:
                raise JsonLimitError(
                    "collection",
                    f"object exceeds {self.max_collection_items} members",
                )
            if count > 1:
                self.token(",")
            if not isinstance(key, str):
                raise JsonLimitError("key", "object key is not a string")
            self.scalar(key)
            self.token(":")
            self.visit(value, depth=depth + 1)
        self.token("}")

    def visit(self, value: Any, *, depth: int = 0) -> None:
        if depth > self.max_depth:
            raise JsonLimitError("depth", f"JSON exceeds depth {self.max_depth}")
        if value is None or isinstance(value, (str, bool, int, float)):
            self.scalar(value)
            return
        if isinstance(value, (list, tuple)):
            if len(value) > self.max_collection_items:
                raise JsonLimitError(
                    "collection",
                    f"array exceeds {self.max_collection_items} members",
                )
            self._value()
            self.token("[")
            for index, item in enumerate(value):
                if index:
                    self.token(",")
                self.visit(item, depth=depth + 1)
            self.token("]")
            return
        if isinstance(value, Mapping):
            self.object_fields(value.items(), depth=depth)
            return
        raise JsonLimitError("type", f"unsupported JSON type {type(value).__name__}")


def bounded_json_size(
    value: Any,
    *,
    max_bytes: int,
    max_depth: int,
    max_string_chars: int,
    max_collection_items: int,
    max_values: int,
) -> int:
    budget = JsonBudget(
        max_bytes,
        max_depth,
        max_string_chars,
        max_collection_items,
        max_values,
    )
    budget.visit(value)
    return budget.used
