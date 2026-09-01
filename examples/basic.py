import streamlit as st
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeStyle,
    NodeType,
    PaletteTone,
    graph_canvas,
)

st.set_page_config(page_title="Graph Canvas example", layout="wide")
st.title("Streamlit Graph Canvas")

schema = GraphSchema(
    node_types={
        "service": NodeType("service", NodeStyle(fill="surface", stroke="accent")),
        "store": NodeType("store", NodeStyle(fill="surface", stroke="border")),
    },
    edge_types={"uses": EdgeType("uses")},
    palette={"accent": PaletteTone("var(--st-primary-color)")},
)
graph = GraphData(
    nodes=(
        Node("api", "service", "Public API"),
        Node("worker", "service", "Worker"),
        Node("database", "store", "Database"),
    ),
    edges=(
        Edge("api-worker", "api", "worker", "uses"),
        Edge("worker-db", "worker", "database", "uses"),
    ),
)

result = graph_canvas(graph, schema, key="basic-graph")
st.write("Selected nodes", result.selected_node_ids)
