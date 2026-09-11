"""Exercise expansion and budget changes independently from input limits."""

import streamlit as st
from streamlit_graph_canvas import (
    ChildGroup,
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    graph_canvas,
)

budget = st.number_input("Display budget", min_value=1, value=20, step=1)
schema = GraphSchema(
    {
        "owner": NodeType("owner", child_groups=(ChildGroup("direct", "Members"),)),
        "member": NodeType("member"),
    },
    {"direct": EdgeType("direct"), "requires": EdgeType("requires")},
)
graph = GraphData(
    (
        Node("owner", "owner", "Collection"),
        *(Node(f"m{i}", "member", f"Member {i}") for i in range(30)),
    ),
    (
        *(Edge(f"d{i}", "owner", f"m{i}", "direct") for i in range(30)),
        *(Edge(f"r{i}", f"m{i}", f"m{i + 1}", "requires") for i in range(29)),
    ),
)
graph_canvas(
    graph, schema, key="budget", max_elements=int(budget), navigation_anchor="owner"
)
