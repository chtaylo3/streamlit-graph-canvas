"""Declarative browser-local search and explicit app-side search requests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal, cast

from .model import GraphData


@dataclass(frozen=True, slots=True)
class SearchField:
    """Search a scalar key in Node.data; omitted or null values are unknown."""

    key: str
    label: str
    kind: Literal["text", "number", "choice"] = "text"
    choices: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key or self.key.startswith("$"):
            raise ValueError(
                "SearchField.key must be a nonempty, non-reserved data key"
            )
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("SearchField.label must be nonempty")
        if self.kind not in {"text", "number", "choice"}:
            raise ValueError("SearchField.kind must be text, number, or choice")
        if not isinstance(self.description, str):
            raise ValueError("SearchField.description must be text")
        if not isinstance(self.choices, tuple) or not all(
            isinstance(c, str) for c in self.choices
        ):
            raise ValueError("SearchField.choices must be a tuple of strings")
        if self.kind == "choice" and not self.choices:
            raise ValueError("Choice fields need at least one choice")


@dataclass(frozen=True, slots=True)
class SearchCriterion:
    field: str
    operator: str
    value: str | float | int | None


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """One explicit submission; matching IDs are browser results, not authorization."""

    query: str
    criteria: tuple[SearchCriterion, ...]
    match_mode: Literal["all", "any"]
    include_context: bool
    matching_node_ids: tuple[str, ...]
    sequence: int


def parse_search_request(
    raw: Any,
    graph: GraphData,
    fields: tuple[SearchField, ...],
    *,
    topology_revision: int,
    presentation_revision: int,
    acknowledged: int,
) -> SearchRequest | None:
    if not isinstance(raw, Mapping):
        return None
    sequence = raw.get("sequence")
    if type(sequence) is not int or sequence <= acknowledged:
        return None
    if (
        raw.get("topologyRevision") != topology_revision
        or raw.get("presentationRevision") != presentation_revision
    ):
        return None
    query, criteria, mode = raw.get("query"), raw.get("criteria"), raw.get("matchMode")
    ids, context = raw.get("matchingNodeIds"), raw.get("includeContext")
    if (
        not isinstance(query, str)
        or len(query) > 256
        or not isinstance(mode, str)
        or mode not in {"all", "any"}
    ):
        return None
    if type(context) is not bool or not isinstance(criteria, list) or len(criteria) > 8:
        return None
    known_ids = {n.id for n in graph.nodes}
    if (
        not isinstance(ids, list)
        or len(ids) > len(known_ids)
        or not all(isinstance(n, str) and n in known_ids for n in ids)
    ):
        return None
    kinds = {f.key: f.kind for f in fields} | {"$label": "text"}
    choices = {f.key: f.choices for f in fields}
    parsed = []
    for item in criteria:
        if not isinstance(item, Mapping):
            return None
        key, operator, value = (
            item.get("field"),
            item.get("operator"),
            item.get("value"),
        )
        if (
            not isinstance(key, str)
            or key not in kinds
            or not isinstance(operator, str)
        ):
            return None
        if operator in {"known", "unknown"}:
            value = None
        elif kinds[key] == "number":
            if operator not in {"eq", "gt", "gte", "lt", "lte"} or type(value) not in {
                int,
                float,
            }:
                return None
            try:
                if not isfinite(cast(int | float, value)):
                    return None
            except OverflowError:
                return None
        elif (
            operator not in ({"eq"} if kinds[key] == "choice" else {"eq", "contains"})
            or not isinstance(value, str)
            or len(value) > 256
            or (kinds[key] == "choice" and value not in choices[key])
        ):
            return None
        parsed.append(SearchCriterion(key, operator, value))
    return SearchRequest(
        query,
        tuple(parsed),
        cast(Literal["all", "any"], mode),
        context,
        tuple(dict.fromkeys(ids)),
        sequence,
    )
