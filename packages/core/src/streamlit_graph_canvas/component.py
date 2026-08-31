"""Streamlit Components v2 registration and user-facing mount function."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, TypedDict, cast

from .model import FitView, GraphData, GraphSchema, SelectionMode
from .renderers import RendererRegistry
from .serialization import serialize_graph

CanvasHeight = int | Literal["stretch"]


class _RevisionState(TypedDict):
    topology_hash: str
    presentation_hash: str
    topology_revision: int
    presentation_revision: int


@dataclass(frozen=True, slots=True)
class CanvasResult:
    selected_node_ids: tuple[str, ...]
    viewport: dict[str, float] | None
    actions: tuple[dict[str, Any], ...]
    topology_hash: str
    presentation_hash: str


def _noop() -> None:
    """Keep declared Components v2 state names available without a callback."""


def _revision_state(
    key: str, topology_hash: str, presentation_hash: str
) -> tuple[int, int]:
    import streamlit as st

    state_key = f"_sgc_revisions:{key}"
    previous = st.session_state.get(state_key)
    current: _RevisionState
    if previous is None:
        current = {
            "topology_hash": topology_hash,
            "presentation_hash": presentation_hash,
            "topology_revision": 1,
            "presentation_revision": 1,
        }
    else:
        current = cast(_RevisionState, dict(previous))
        if current["topology_hash"] != topology_hash:
            current["topology_hash"] = topology_hash
            current["topology_revision"] += 1
        if current["presentation_hash"] != presentation_hash:
            current["presentation_hash"] = presentation_hash
            current["presentation_revision"] += 1
    st.session_state[state_key] = current
    return current["topology_revision"], current["presentation_revision"]


@lru_cache(maxsize=1)
def _renderer() -> Callable[..., Any]:
    import streamlit as st

    return st.components.v2.component(
        "streamlit-graph-canvas.graph_canvas",
        html='<div class="sgc-root" role="application"></div>',
        css="index-*.css",
        js="index-*.js",
        isolate_styles=True,
    )


def graph_canvas(
    graph: GraphData,
    schema: GraphSchema,
    *,
    key: str,
    selection: SelectionMode = SelectionMode.SINGLE,
    fit_view: FitView = FitView.INITIAL,
    max_elements: int = 700,
    renderer_registry: RendererRegistry | None = None,
    width: str | int = "stretch",
    height: CanvasHeight = 620,
    on_selected_node_ids_change: Callable[[], None] | None = None,
    on_viewport_change: Callable[[], None] | None = None,
    on_actions_change: Callable[[], None] | None = None,
) -> CanvasResult:
    """Validate and mount a domain-neutral graph canvas."""

    if isinstance(height, int) and height <= 0:
        raise ValueError("height must be a positive pixel value or 'stretch'")
    serialized = serialize_graph(
        schema,
        graph,
        max_elements=max_elements,
        renderer_registry=renderer_registry,
    )
    topology_revision, presentation_revision = _revision_state(
        key, serialized.topology_hash, serialized.presentation_hash
    )
    result = _renderer()(
        key=key,
        data={
            **serialized.envelope,
            "topologyRevision": topology_revision,
            "presentationRevision": presentation_revision,
            "config": {
                "selection": selection.value,
                "fitView": fit_view.value,
                "height": height,
            },
        },
        default={
            "selected_node_ids": [],
            "viewport": None,
            "actions": [],
        },
        width=width,
        height=height,
        on_selected_node_ids_change=on_selected_node_ids_change or _noop,
        on_viewport_change=on_viewport_change or _noop,
        on_actions_change=on_actions_change or _noop,
    )
    return CanvasResult(
        selected_node_ids=tuple(result.selected_node_ids or ()),
        viewport=result.viewport,
        actions=tuple(result.actions or ()),
        topology_hash=serialized.topology_hash,
        presentation_hash=serialized.presentation_hash,
    )
