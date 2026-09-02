from __future__ import annotations

import io
import os

import streamlit as st
from PIL import Image, ImageDraw
from streamlit_graph_canvas import (
    AtlasPolicy,
    AtlasScope,
    BadgeBinding,
    Edge,
    EdgeStyle,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeStyle,
    NodeType,
    PaletteTone,
    PngImage,
    PortSide,
    PortSpec,
    Region,
    SpriteBinding,
    SpriteCatalog,
    SpriteRef,
    StaticSprite,
    Transport,
    ValidationError,
    discover_renderer_diagnostics,
    enable_renderers,
    graph_canvas,
)

set_name = os.environ.get("SGC_CONTRIB_SET", "stock")
with_stock = set_name in {"stock", "transports", "hostile", "multi-canvas"}
with_javascript_fixture = set_name == "transports"
enabled_distributions = []
if with_stock:
    enabled_distributions.append("streamlit-graph-canvas-contrib")
if with_javascript_fixture:
    enabled_distributions.append("scg-javascript-renderer-fixture")
if set_name == "javascript-stale":
    enabled_distributions.append("scg-javascript-stale-renderer-fixture")
if set_name == "javascript-adversarial":
    enabled_distributions.append("scg-javascript-adversarial-renderer-fixture")
renderer_enablement_diagnostic = "none"
if set_name == "javascript-conflict":
    conflict_names = (
        "scg-javascript-conflict-a-renderer-fixture",
        "scg-javascript-conflict-b-renderer-fixture",
    )
    conflict_codes = []
    for order in (conflict_names, tuple(reversed(conflict_names))):
        try:
            enable_renderers(list(order))
        except ValidationError as error:
            conflict_codes.append(error.diagnostic.code)
    renderer_enablement_diagnostic = ",".join(conflict_codes)
registry = enable_renderers(enabled_distributions) if enabled_distributions else None
discovery_diagnostics = discover_renderer_diagnostics()
ownership_diagnostic = "none"
if set_name == "hostile":
    try:
        enable_renderers(["scg-cross-import-renderer-fixture"])
    except ValidationError as error:
        ownership_diagnostic = error.diagnostic.code

st.set_page_config(page_title="Graph Canvas Conformance", layout="wide")
st.title("Graph Canvas Conformance")
st.caption(f"Contrib set: {set_name}")
st.markdown(
    '<div data-testid="discovery-diagnostics">'
    f"{','.join(item.code for item in discovery_diagnostics) or 'none'}</div>",
    unsafe_allow_html=True,
)
st.markdown(
    f'<div data-testid="ownership-diagnostic">{ownership_diagnostic}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div data-testid="renderer-enablement-diagnostic">'
    f"{renderer_enablement_diagnostic}</div>",
    unsafe_allow_html=True,
)

st.session_state.setdefault("presentation", 1)
st.session_state.setdefault("topology", 1)
st.session_state.setdefault("action_sequences", [])
if st.button("Change presentation"):
    st.session_state.presentation += 1
if st.button("Change topology"):
    st.session_state.topology += 1
mount_secondary = (
    st.checkbox("Mount secondary canvas", value=True)
    if set_name == "multi-canvas"
    else False
)


def sprite_png(color: tuple[int, int, int, int], mark: str) -> PngImage:
    image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((1, 1, 22, 22), fill=color)
    draw.text((8, 6), mark, fill=(255, 255, 255, 255))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return PngImage.from_bytes(output.getvalue())


sprite_catalog = (
    SpriteCatalog(
        {
            "api": StaticSprite(
                light=sprite_png((220, 38, 38, 180), "L"),
                dark=sprite_png((37, 99, 235, 180), "D"),
            ),
            "worker": StaticSprite(
                # No dark image: this is the deterministic light fallback case.
                light=sprite_png((22, 163, 74, 150), "F")
            ),
        }
    )
    if with_stock
    else None
)

badges = (
    (
        BadgeBinding(
            "count-prims",
            "streamlit-graph-canvas/contrib/count-chip",
            Region.at(145, -8, 42, 22),
            required=True,
        ),
        BadgeBinding(
            "count-javascript",
            "streamlit-graph-canvas/contrib/count-chip",
            Region.at(145, 19, 42, 22),
            transport=Transport.JAVASCRIPT,
            required=True,
        ),
        BadgeBinding(
            "count-atlas",
            "streamlit-graph-canvas/contrib/count-chip",
            Region.at(145, 46, 42, 22),
            transport=Transport.ATLAS,
            required=True,
        ),
    )
    if with_stock
    else ()
)
if with_javascript_fixture:
    badges += (
        BadgeBinding(
            "javascript-only",
            "streamlit-graph-canvas/fixture/javascript-only",
            Region.at(112, 46, 22, 22),
            transport=Transport.JAVASCRIPT,
            required=True,
        ),
    )
if set_name == "javascript-stale":
    badges += (
        BadgeBinding(
            "javascript-stale",
            "streamlit-graph-canvas/fixture/javascript-stale",
            Region.at(112, 46, 22, 22),
            transport=Transport.JAVASCRIPT,
            required=False,
        ),
    )
if set_name == "javascript-adversarial":
    badges += tuple(
        BadgeBinding(
            f"javascript-{behavior}",
            "streamlit-graph-canvas/fixture/javascript-adversarial",
            Region.at(95 + index * 24, 46, 22, 22),
            transport=Transport.JAVASCRIPT,
            required=False,
        )
        for index, behavior in enumerate(
            (
                "listener-leak",
                "dom-mutation",
                "factory-throw",
                "render-throw",
                "cleanup-throw",
                "healthy",
            )
        )
    )
schema = GraphSchema(
    node_types={
        "service": NodeType(
            "service",
            style=NodeStyle(
                fill="node_surface",
                stroke="accent",
                text="node_text",
                radius=16,
            ),
            ports=(
                PortSpec("in", PortSide.TOP, "input"),
                PortSpec("out", PortSide.BOTTOM, "output"),
            ),
            badges=badges,
            sprites=(SpriteBinding("thumbnail", Region.at(8, 48, 24, 24), z=10),)
            if with_stock
            else (),
        )
    },
    edge_types={"calls": EdgeType("calls", style=EdgeStyle("edge", 2.5, True))},
    palette={
        "accent": PaletteTone("#2563eb", "#60a5fa"),
        "on_accent": PaletteTone("#ffffff", "#0f172a"),
        "node_surface": PaletteTone("#f8fafc", "#0f172a"),
        "node_text": PaletteTone("#0f172a", "#f8fafc"),
        "edge": PaletteTone("#dc2626", "#f87171"),
    },
)
api_badges = (
    {"count-prims": 7, "count-javascript": 7, "count-atlas": 7} if with_stock else {}
)
worker_badges = (
    {"count-prims": 2, "count-javascript": 2, "count-atlas": 2} if with_stock else {}
)
if with_javascript_fixture:
    api_badges["javascript-only"] = "API status"
    worker_badges["javascript-only"] = "Worker status"
if set_name == "javascript-stale":
    api_badges["javascript-stale"] = "stale"
if set_name == "javascript-adversarial":
    api_badges.update(
        {
            f"javascript-{behavior}": behavior
            for behavior in (
                "listener-leak",
                "dom-mutation",
                "factory-throw",
                "render-throw",
                "cleanup-throw",
                "healthy",
            )
        }
    )

nodes = [
    Node(
        "api",
        "service",
        f"API v{st.session_state.presentation}",
        badges=api_badges,
        sprites={"thumbnail": SpriteRef("api", "API themed status image")}
        if with_stock
        else {},
    ),
    Node(
        "worker",
        "service",
        "Worker",
        badges=worker_badges,
        sprites={"thumbnail": SpriteRef("worker", "Worker fallback status image")}
        if with_stock
        else {},
    ),
]
if st.session_state.topology > 1:
    nodes.append(
        Node(
            "cache",
            "service",
            "Cache",
            badges={
                "count-prims": 1,
                "count-javascript": 1,
                "count-atlas": 1,
                **(
                    {"javascript-only": "Cache status"}
                    if with_javascript_fixture
                    else {}
                ),
            }
            if with_stock
            else {},
        )
    )
edges = [Edge("api-worker", "api", "worker", "calls", "out", "in")]
if len(nodes) == 3:
    edges.append(Edge("worker-cache", "worker", "cache", "calls", "out", "in"))

graph = GraphData(tuple(nodes), tuple(edges))
atlas_policy = AtlasPolicy(
    scope=AtlasScope.TENANT,
    max_pages=32,
    max_bytes=8 * 1024 * 1024,
    max_tenant_pages=16,
    max_tenant_bytes=4 * 1024 * 1024,
)
try:
    result = graph_canvas(
        graph,
        schema,
        key="conformance-canvas",
        renderer_registry=registry,
        sprite_catalog=sprite_catalog,
        atlas_policy=atlas_policy,
        atlas_tenant="conformance-tenant",
    )
except ValidationError as error:
    if (
        os.environ.get("SGC_EXPECT_PILLOW_FAILURE") == "true"
        and error.diagnostic.code == "SGC_ATLAS_DEPENDENCY_VERSION"
    ):
        st.markdown(
            '<div data-testid="pillow-forward-diagnostic">'
            f"{error.diagnostic.code}</div>",
            unsafe_allow_html=True,
        )
        st.stop()
    raise
if mount_secondary:
    graph_canvas(
        graph,
        schema,
        key="conformance-canvas-secondary",
        renderer_registry=registry,
        sprite_catalog=sprite_catalog,
        atlas_policy=atlas_policy,
        atlas_tenant="conformance-tenant-secondary",
    )
for action in result.actions:
    if action.seq not in st.session_state.action_sequences:
        st.session_state.action_sequences.append(action.seq)
st.markdown(
    f'<div data-testid="selected-nodes">{",".join(result.selected_node_ids)}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div data-testid="action-count">{len(result.actions)}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div data-testid="action-sequences">'
    f"{','.join(map(str, st.session_state.action_sequences))}</div>",
    unsafe_allow_html=True,
)
viewport = (
    "none"
    if result.viewport is None
    else f"{result.viewport.x:.3f},{result.viewport.y:.3f},{result.viewport.zoom:.3f}"
)
st.markdown(
    f'<div data-testid="viewport-state">{viewport}</div>',
    unsafe_allow_html=True,
)
