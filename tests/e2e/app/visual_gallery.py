"""Static scenes for visual regression snapshots.

Each scene is chosen with the ``scene`` query parameter so a snapshot test opens
exactly one canvas with no interactive setup. Motion is disabled so screenshots
never catch a transition mid-frame.
"""

import streamlit as st
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    FitView,
    GraphData,
    GraphSchema,
    Node,
    NodeStyle,
    NodeType,
    PaletteTone,
    SearchField,
    graph_canvas,
)

st.set_page_config(page_title="Visual Gallery", layout="wide")
st.title("Visual Gallery")
scene = st.query_params.get("scene", "default")

schema = GraphSchema(
    node_types={
        "service": NodeType("service", NodeStyle(fill="surface", stroke="accent")),
        "store": NodeType("store", NodeStyle(fill="surface", stroke="border")),
    },
    edge_types={"calls": EdgeType("calls")},
    palette={"accent": PaletteTone("var(--st-primary-color)")},
)
graph = GraphData(
    (
        Node("api", "service", "Public API", data={"tier": 1}),
        Node("worker", "service", "Worker", data={"tier": 2}),
        Node("scheduler", "service", "Scheduler", data={"tier": 2}, disabled=True),
        Node("cache", "store", "Cache", data={"tier": 3}, dimmed=True),
        Node("db", "store", "Database", data={"tier": 3}),
    ),
    (
        Edge("api-worker", "api", "worker", "calls"),
        Edge("api-cache", "api", "cache", "calls"),
        Edge("scheduler-worker", "scheduler", "worker", "calls"),
        Edge("worker-db", "worker", "db", "calls"),
    ),
)

graph_canvas(
    graph,
    schema,
    key=f"visual-{scene}",
    fit_view=FitView.INITIAL,
    transition_ms=0,
    search_fields=(SearchField("tier", "Tier", "number"),),
    height=420,
)
