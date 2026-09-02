"""Streamlit Components v2 registration and user-facing mount function."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Literal, TypedDict, cast

from .atlas import (
    AtlasCache,
    AtlasPolicy,
    AtlasScope,
    resolution_bucket,
    tenant_atlas_cache,
)
from .contract import RENDERER_API
from .images import SpriteCatalog
from .model import FitView, GraphData, GraphSchema, SelectionMode
from .protocol import (
    CanvasAction,
    CanvasViewport,
    parse_actions,
    parse_selection,
    parse_viewport,
)
from .renderers import RendererRegistry
from .serialization import serialize_graph

CanvasDimension = int | Literal["stretch"]
LOGGER = logging.getLogger("streamlit_graph_canvas")


class _CanvasSessionState(TypedDict):
    topology_hash: str
    presentation_hash: str
    topology_revision: int
    presentation_revision: int
    selected_node_ids: list[str]
    viewport: dict[str, float] | None
    acknowledged_sequence: int
    atlas_theme: str
    atlas_resolution: float
    atlas_page_ids: list[str]
    atlas_cache: AtlasCache | None


@dataclass(frozen=True, slots=True)
class CanvasResult:
    selected_node_ids: tuple[str, ...]
    viewport: CanvasViewport | None
    actions: tuple[CanvasAction, ...]
    topology_hash: str
    presentation_hash: str


def _noop() -> None:
    """Keep declared Components v2 state names available without a callback."""


def _revision_state(
    key: str, topology_hash: str, presentation_hash: str
) -> _CanvasSessionState:
    import streamlit as st

    state_key = f"_sgc:{key}"
    previous = st.session_state.get(state_key)
    current: _CanvasSessionState
    if previous is None:
        current = {
            "topology_hash": topology_hash,
            "presentation_hash": presentation_hash,
            "topology_revision": 1,
            "presentation_revision": 1,
            "selected_node_ids": [],
            "viewport": None,
            "acknowledged_sequence": 0,
            "atlas_theme": "light",
            "atlas_resolution": 1.0,
            "atlas_page_ids": [],
            "atlas_cache": None,
        }
    else:
        current = cast(_CanvasSessionState, dict(previous))
        current.setdefault("selected_node_ids", [])
        current.setdefault("viewport", None)
        current.setdefault("acknowledged_sequence", 0)
        current.setdefault("atlas_theme", "light")
        current.setdefault("atlas_resolution", 1.0)
        current.setdefault("atlas_page_ids", [])
        current.setdefault("atlas_cache", None)
        if current["topology_hash"] != topology_hash:
            current["topology_hash"] = topology_hash
            current["topology_revision"] += 1
        if current["presentation_hash"] != presentation_hash:
            current["presentation_hash"] = presentation_hash
            current["presentation_revision"] += 1
    st.session_state[state_key] = current
    return current


def _store_session_state(key: str, state: _CanvasSessionState) -> None:
    import streamlit as st

    st.session_state[f"_sgc:{key}"] = state


@lru_cache(maxsize=1)
def _renderer() -> Callable[..., Any]:
    import streamlit as st

    return st.components.v2.component(
        "streamlit-graph-canvas.graph_canvas",
        html='<div class="sgc-root" aria-label="Graph canvas"></div>',
        css="index-*.css",
        js="index-*.js",
        isolate_styles=True,
    )


@lru_cache(maxsize=64)
def _javascript_bootstrap(component: str, entry: str) -> Callable[..., Any]:
    import streamlit as st

    return st.components.v2.component(
        component,
        js=entry,
        isolate_styles=True,
    )


def _mount_javascript_bootstraps(
    registry: RendererRegistry | None, *, key: str
) -> None:
    if registry is None:
        return
    components: dict[tuple[str, str], list[dict[str, object]]] = {}
    for renderer in registry.renderers.values():
        declaration = renderer.declaration
        if (
            "javascript" not in declaration.transports
            or declaration.javascript_component is None
            or declaration.javascript_entry is None
            or renderer.javascript_hash is None
        ):
            continue
        components.setdefault(
            (declaration.javascript_component, declaration.javascript_entry), []
        ).append(
            {
                "kind": declaration.kind,
                "rendererApi": RENDERER_API,
                "version": renderer.version,
                "assetHash": renderer.javascript_hash,
                "buildIdentity": declaration.javascript_identity,
            }
        )
    for index, ((component, entry), registrations) in enumerate(
        sorted(components.items())
    ):
        _javascript_bootstrap(component, entry)(
            key=f"{key}:renderer-bootstrap:{index}",
            data={"registrations": registrations},
            width=1,
            height=0,
        )


def _browser_atlas_state(result: Any) -> tuple[str, float, list[str]]:
    theme = getattr(result, "atlas_theme", "light")
    if theme not in {"light", "dark"}:
        theme = "light"
    raw_resolution = getattr(result, "atlas_resolution", 1.0)
    if isinstance(raw_resolution, bool) or not isinstance(raw_resolution, (int, float)):
        raw_resolution = 1.0
    resolution = resolution_bucket(float(raw_resolution))
    raw_pages = getattr(result, "atlas_page_ids", [])
    pages = (
        list(dict.fromkeys(raw_pages))
        if isinstance(raw_pages, list)
        and len(raw_pages) <= 512
        and all(isinstance(item, str) and len(item) == 64 for item in raw_pages)
        else []
    )
    return theme, resolution, pages


def graph_canvas(
    graph: GraphData,
    schema: GraphSchema,
    *,
    key: str,
    selection: SelectionMode = SelectionMode.SINGLE,
    fit_view: FitView = FitView.INITIAL,
    max_elements: int = 700,
    renderer_registry: RendererRegistry | None = None,
    sprite_catalog: SpriteCatalog | None = None,
    width: CanvasDimension = "stretch",
    height: CanvasDimension = 620,
    on_selected_node_ids_change: Callable[[], None] | None = None,
    on_viewport_change: Callable[[], None] | None = None,
    on_actions_change: Callable[[], None] | None = None,
    atlas_policy: AtlasPolicy | None = None,
    atlas_tenant: str | None = None,
) -> CanvasResult:
    """Validate and mount a domain-neutral graph canvas."""

    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not (
            value == "stretch" or (isinstance(value, int) and value > 0)
        ):
            raise ValueError(
                f"{name} must be a positive integer pixel value or 'stretch'"
            )
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty string")
    if not isinstance(selection, SelectionMode):
        raise ValueError("selection must be a SelectionMode")
    if not isinstance(fit_view, FitView):
        raise ValueError("fit_view must be a FitView")
    atlas_policy = atlas_policy or AtlasPolicy()
    if not isinstance(atlas_policy, AtlasPolicy):
        raise ValueError("atlas_policy must be an AtlasPolicy")
    if atlas_policy.scope is AtlasScope.TENANT:
        if (
            not isinstance(atlas_tenant, str)
            or not atlas_tenant
            or len(atlas_tenant) > 128
        ):
            raise ValueError(
                "tenant-scoped ATLAS requires a non-empty atlas_tenant of at most "
                "128 chars"
            )
    elif atlas_tenant is not None:
        raise ValueError("atlas_tenant is valid only with AtlasScope.TENANT")
    import streamlit as st

    previous = st.session_state.get(f"_sgc:{key}", {})
    atlas_theme = previous.get("atlas_theme", "light")
    atlas_resolution = previous.get("atlas_resolution", 1.0)
    atlas_page_ids = previous.get("atlas_page_ids", [])
    if atlas_policy.scope is AtlasScope.TENANT:
        tenant = cast(str, atlas_tenant)
        atlas_lease = tenant_atlas_cache(atlas_policy)
        atlas_cache = atlas_lease.cache
    else:
        atlas_lease = None
        atlas_cache = previous.get("atlas_cache")
        if atlas_cache is None or atlas_cache.policy != atlas_policy:
            atlas_cache = AtlasCache(atlas_policy)
        tenant = f"session:{key}"
    try:
        serialized = serialize_graph(
            schema,
            graph,
            max_elements=max_elements,
            renderer_registry=renderer_registry,
            sprite_catalog=sprite_catalog,
            atlas_cache=atlas_cache,
            atlas_policy=atlas_policy,
            atlas_tenant=tenant,
            atlas_theme=atlas_theme,
            atlas_resolution=atlas_resolution,
            atlas_known_pages=frozenset(atlas_page_ids),
        )
    finally:
        if atlas_lease is not None:
            atlas_lease.close()
    session = _revision_state(
        key, serialized.topology_hash, serialized.presentation_hash
    )
    session["atlas_cache"] = (
        atlas_cache if atlas_policy.scope is AtlasScope.SESSION else None
    )
    topology_revision = session["topology_revision"]
    presentation_revision = session["presentation_revision"]
    _mount_javascript_bootstraps(renderer_registry, key=key)
    result = _renderer()(
        key=key,
        data={
            **serialized.envelope,
            "topologyRevision": topology_revision,
            "presentationRevision": presentation_revision,
            "state": {
                "selectedNodeIds": session["selected_node_ids"],
                "viewport": session["viewport"],
                "acknowledgedSeq": session["acknowledged_sequence"],
                "atlasTheme": session["atlas_theme"],
                "atlasResolution": session["atlas_resolution"],
                "atlasPageIds": session["atlas_page_ids"],
            },
            "config": {
                "selection": selection.value,
                "fitView": fit_view.value,
                "height": height,
            },
        },
        default={
            "selected_node_ids": session["selected_node_ids"],
            "viewport": session["viewport"],
            "atlas_theme": session["atlas_theme"],
            "atlas_resolution": session["atlas_resolution"],
            "atlas_page_ids": session["atlas_page_ids"],
        },
        width=width,
        height=height,
        on_selected_node_ids_change=on_selected_node_ids_change or _noop,
        on_viewport_change=on_viewport_change or _noop,
        on_actions_change=on_actions_change or _noop,
        on_atlas_theme_change=_noop,
        on_atlas_resolution_change=_noop,
        on_atlas_page_ids_change=_noop,
    )
    selected_node_ids = parse_selection(
        getattr(result, "selected_node_ids", session["selected_node_ids"]), graph
    )
    viewport = parse_viewport(getattr(result, "viewport", session["viewport"]))
    actions, acknowledged = parse_actions(
        getattr(result, "actions", None),
        graph,
        topology_revision=topology_revision,
        acknowledged_sequence=session["acknowledged_sequence"],
    )
    session["selected_node_ids"] = list(selected_node_ids)
    session["viewport"] = asdict(viewport) if viewport is not None else None
    session["acknowledged_sequence"] = acknowledged
    previous_atlas_theme = session["atlas_theme"]
    previous_atlas_resolution = session["atlas_resolution"]
    atlas_theme, atlas_resolution, atlas_page_ids = _browser_atlas_state(result)
    session["atlas_theme"] = atlas_theme
    session["atlas_resolution"] = atlas_resolution
    session["atlas_page_ids"] = atlas_page_ids
    _store_session_state(key, session)
    if (
        atlas_theme != previous_atlas_theme
        or atlas_resolution != previous_atlas_resolution
    ):
        # Components state is returned after this run's envelope was serialized.
        # Apply a presentation-only rerun so the selected theme/DPR reaches the
        # rasterizer instead of waiting for an unrelated user interaction.
        st.rerun()
    if actions:
        LOGGER.info(
            "Accepted canvas actions",
            extra={
                "sgc_event_code": "SGC_ACTION_ACCEPTED",
                "sgc_action_count": len(actions),
                "sgc_topology_revision": topology_revision,
            },
        )
    return CanvasResult(
        selected_node_ids=selected_node_ids,
        viewport=viewport,
        actions=actions,
        topology_hash=serialized.topology_hash,
        presentation_hash=serialized.presentation_hash,
    )
