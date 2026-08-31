from __future__ import annotations

import os

import streamlit as st
from streamlit_graph_canvas import (
    BadgeBinding,
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PaletteTone,
    Region,
    enable_renderers,
    graph_canvas,
)

set_name = os.environ.get("SGC_CONTRIB_SET", "stock")
with_stock = set_name != "core-only"
registry = enable_renderers(["streamlit-graph-canvas-contrib"]) if with_stock else None

st.set_page_config(page_title="Graph Canvas Conformance", layout="wide")
st.title("Graph Canvas Conformance")
st.caption(f"Contrib set: {set_name}")

st.session_state.setdefault("presentation", 1)
st.session_state.setdefault("topology", 1)
if st.button("Change presentation"):
    st.session_state.presentation += 1
if st.button("Change topology"):
    st.session_state.topology += 1

badges = (
    (
        BadgeBinding(
            "count",
            "streamlit-graph-canvas/contrib/count-chip",
            Region.at(145, -8, 42, 22),
            required=True,
        ),
    )
    if with_stock
    else ()
)
schema = GraphSchema(
    node_types={"service": NodeType("service", badges=badges)},
    edge_types={"calls": EdgeType("calls")},
    palette={
        "accent": PaletteTone("#2563eb", "#60a5fa"),
        "on_accent": PaletteTone("#ffffff", "#0f172a"),
    },
)
nodes = [
    Node(
        "api",
        "service",
        f"API v{st.session_state.presentation}",
        badges={"count": 7} if with_stock else {},
    ),
    Node(
        "worker",
        "service",
        "Worker",
        badges={"count": 2} if with_stock else {},
    ),
]
if st.session_state.topology > 1:
    nodes.append(
        Node(
            "cache",
            "service",
            "Cache",
            badges={"count": 1} if with_stock else {},
        )
    )
edges = [Edge("api-worker", "api", "worker", "calls")]
if len(nodes) == 3:
    edges.append(Edge("worker-cache", "worker", "cache", "calls"))

result = graph_canvas(
    GraphData(tuple(nodes), tuple(edges)),
    schema,
    key="conformance-canvas",
    renderer_registry=registry,
)
st.markdown(
    f'<div data-testid="selected-nodes">{",".join(result.selected_node_ids)}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div data-testid="action-count">{len(result.actions)}</div>',
    unsafe_allow_html=True,
)
