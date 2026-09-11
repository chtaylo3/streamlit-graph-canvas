"""Streamlit Components v2 registration and user-facing mount function."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Literal, TypedDict, cast

from .atlas import AtlasPolicy, atlas_cache, resolution_bucket
from .contract import RENDERER_API
from .csp import telemetry_origin
from .errors import Diagnostic, ValidationError
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
from .search import SearchField, SearchRequest, parse_search_request
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
    search_acknowledged_sequence: int


@dataclass(frozen=True, slots=True)
class CanvasResult:
    selected_node_ids: tuple[str, ...]
    viewport: CanvasViewport | None
    actions: tuple[CanvasAction, ...]
    topology_hash: str
    presentation_hash: str
    search_request: SearchRequest | None = None


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
            "search_acknowledged_sequence": 0,
        }
    else:
        current = cast(_CanvasSessionState, dict(previous))
        current.setdefault("search_acknowledged_sequence", 0)
        current.setdefault("selected_node_ids", [])
        current.setdefault("viewport", None)
        current.setdefault("acknowledged_sequence", 0)
        current.setdefault("atlas_theme", "light")
        current.setdefault("atlas_resolution", 1.0)
        current.setdefault("atlas_page_ids", [])
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
    transition_ms: int = 250,
    navigation_anchor: str | None = None,
    max_elements: int = 700,
    max_loaded_elements: int | None = None,
    search_fields: tuple[SearchField, ...] | None = None,
    search_active_ids: tuple[str, ...] | None = None,
    on_search_request: Callable[[], None] | None = None,
    search_reorder_threshold: int | None = None,
    search_nonmatch_opacity: float | None = None,
    renderer_registry: RendererRegistry | None = None,
    sprite_catalog: SpriteCatalog | None = None,
    width: CanvasDimension = "stretch",
    height: CanvasDimension = 620,
    on_selected_node_ids_change: Callable[[], None] | None = None,
    on_viewport_change: Callable[[], None] | None = None,
    on_actions_change: Callable[[], None] | None = None,
    atlas_policy: AtlasPolicy | None = None,
    telemetry_endpoint: str | None = None,
    atlas_tenant: str | None = None,
) -> CanvasResult:
    """Validate and mount a domain-neutral graph canvas.

    ``transition_ms`` sets motion duration (0 disables it; default 250 ms).
    Reduced-motion browser preferences disable animation automatically.
    ``navigation_anchor`` identifies a shared node to align between layouts.
    New layouts are prepared while the previous scene remains visible.

    ``max_elements`` limits rendered nodes and edges after collection grouping.
    Collapsed members and replaced parent-to-member edges do not consume it.
    ``max_loaded_elements`` separately caps input nodes plus edges (default:
    the greater of 20,000 and ``max_elements``). Collection counts include all
    loaded members, even when expansion is limited by the display budget.

    ``search_fields=()`` enables local name search; SearchField entries expose
    scalar Node.data values as filters. ``search_active_ids`` explicitly scopes
    the default search; None includes all displayed real nodes. Hidden collection
    members are excluded. Typing and filtering do not send Streamlit events.

    ``search_reorder_threshold`` enables Apply search for peer groups with at
    least that many searched, displayed nodes. Typing never reorders; Apply
    ranks matches first subject to dependency layers, and Clear restores normal
    ordering. ``search_nonmatch_opacity`` optionally dims nonmatches (0 to 1).

    ``on_search_request`` enables an explicit "Send filters to app" button.
    WARNING: pressing it sends a component event and triggers a Streamlit rerun
    (or fragment rerun), potentially repeating queries, computation, and rendering.
    It is never called on each keystroke. The returned CanvasResult.search_request
    contains the accepted submission for app-side work. Cache expensive work and
    send updated Node.data in the subsequent render; do not enable a callback
    for ordinary local filtering.

    Set ``telemetry_endpoint`` to an OTLP/HTTP collector URL to receive
    browser-side metrics. The browser posts directly to that URL rather than
    tunnelling through Streamlit's widget channel, which would force a script
    rerun per flush, so the host CSP must allow the collector origin in
    ``connect-src``. Pass the same URL to
    :func:`~streamlit_graph_canvas.streamlit_host_csp` to obtain that policy.
    """

    if search_reorder_threshold is not None and (
        type(search_reorder_threshold) is not int or search_reorder_threshold < 1
    ):
        raise ValueError("search_reorder_threshold must be a positive integer or None")
    if search_nonmatch_opacity is not None and (
        isinstance(search_nonmatch_opacity, bool)
        or not isinstance(search_nonmatch_opacity, (int, float))
        or not 0 <= search_nonmatch_opacity <= 1
    ):
        raise ValueError("search_nonmatch_opacity must be between 0 and 1 or None")
    if search_fields is not None:
        if (
            not isinstance(search_fields, tuple)
            or len(search_fields) > 32
            or not all(isinstance(f, SearchField) for f in search_fields)
        ):
            raise ValueError(
                "search_fields must be a tuple of at most 32 SearchField values"
            )
        if len({f.key for f in search_fields}) != len(search_fields):
            raise ValueError("search_fields keys must be unique")
    if search_active_ids is not None:
        known_ids = {n.id for n in graph.nodes}
        if not isinstance(search_active_ids, tuple) or not all(
            isinstance(n, str) and n in known_ids for n in search_active_ids
        ):
            raise ValueError("search_active_ids must contain graph node IDs")
    if on_search_request is not None and (
        not callable(on_search_request) or search_fields is None
    ):
        raise ValueError("on_search_request requires enabled search and a callable")
    for budget_name, budget_value in (
        ("max_elements", max_elements),
        ("max_loaded_elements", max_loaded_elements),
    ):
        if budget_name == "max_loaded_elements" and budget_value is None:
            continue
        if (
            isinstance(budget_value, bool)
            or not isinstance(budget_value, int)
            or budget_value <= 0
        ):
            raise ValueError(f"{budget_name} must be a positive integer")
    loaded_limit = (
        max_loaded_elements
        if max_loaded_elements is not None
        else max(20_000, max_elements)
    )
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
    if (
        isinstance(transition_ms, bool)
        or not isinstance(transition_ms, int)
        or not 0 <= transition_ms <= 1000
    ):
        raise ValueError("transition_ms must be an integer from 0 to 1000")
    if navigation_anchor is not None and not isinstance(navigation_anchor, str):
        raise ValueError("navigation_anchor must be a node ID string or None")
    if atlas_tenant is not None:
        raise ValidationError(
            Diagnostic(
                "SGC_ATLAS_TENANT_REMOVED",
                "atlas_tenant is no longer accepted because the atlas cache is "
                "content-addressed and shared by every session in the process.",
                "Remove atlas_tenant and any AtlasScope or per-tenant limit from "
                "AtlasPolicy. See docs/transports-and-csp.md.",
                "ATLAS",
            )
        )
    atlas_policy = atlas_policy or AtlasPolicy()
    if not isinstance(atlas_policy, AtlasPolicy):
        raise ValueError("atlas_policy must be an AtlasPolicy")
    if telemetry_endpoint is not None:
        # Validating here means a misconfigured endpoint fails at mount rather
        # than silently dropping browser metrics, and it rejects the credential
        # and wildcard forms that would be unusable in a CSP source anyway.
        telemetry_origin(telemetry_endpoint)
    import streamlit as st

    previous = st.session_state.get(f"_sgc:{key}", {})
    atlas_theme = previous.get("atlas_theme", "light")
    atlas_resolution = previous.get("atlas_resolution", 1.0)
    atlas_page_ids = previous.get("atlas_page_ids", [])
    serialized = serialize_graph(
        schema,
        graph,
        max_elements=loaded_limit,
        renderer_registry=renderer_registry,
        sprite_catalog=sprite_catalog,
        atlas_cache=atlas_cache(atlas_policy),
        atlas_policy=atlas_policy,
        atlas_theme=atlas_theme,
        atlas_resolution=atlas_resolution,
        atlas_known_pages=frozenset(atlas_page_ids),
    )
    session = _revision_state(
        key, serialized.topology_hash, serialized.presentation_hash
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
                "searchAcknowledgedSeq": session["search_acknowledged_sequence"],
            },
            "config": {
                "selection": selection.value,
                "fitView": fit_view.value,
                "transitionMs": transition_ms,
                "navigationAnchor": navigation_anchor,
                "maxElements": max_elements,
                "search": None
                if search_fields is None
                else {
                    "fields": [asdict(f) for f in search_fields],
                    "activeIds": search_active_ids,
                    "callbackEnabled": on_search_request is not None,
                    "reorderThreshold": search_reorder_threshold,
                    "nonmatchOpacity": search_nonmatch_opacity,
                },
                "height": height,
                "telemetryEndpoint": telemetry_endpoint,
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
        on_search_request_change=on_search_request or _noop,
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
    search_request = (
        parse_search_request(
            getattr(result, "search_request", None),
            graph,
            search_fields or (),
            topology_revision=topology_revision,
            presentation_revision=presentation_revision,
            acknowledged=session["search_acknowledged_sequence"],
        )
        if on_search_request is not None
        else None
    )
    if search_request is not None:
        session["search_acknowledged_sequence"] = search_request.sequence
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
        search_request=search_request,
        topology_hash=serialized.topology_hash,
        presentation_hash=serialized.presentation_hash,
    )
