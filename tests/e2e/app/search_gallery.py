"""Search preview, explicit ordering, and callback conformance."""

import streamlit as st
from streamlit_graph_canvas import (
    ChildGroup,
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    SearchField,
    graph_canvas,
)

st.session_state.runs = st.session_state.get("runs", 0) + 1
st.text(f"Runs: {st.session_state.runs}")
callback = st.checkbox("Enable search callback")
collect = st.checkbox("Collect children")
alpha_count = st.number_input("Alpha count", min_value=0, value=0)


def sent():
    st.session_state.sent = st.session_state.get("sent", 0) + 1


st.text(f"Sent: {st.session_state.get('sent', 0)}")
graph = GraphData(
    (
        Node("root", "root", "Root"),
        *(
            Node(n, "package", n, data={"count": alpha_count if n == "alpha" else i})
            for i, n in enumerate(("alpha", "beta", "gamma", "context"))
        ),
    ),
    tuple(Edge(n, "root", n, "child") for n in ("alpha", "beta", "gamma", "context")),
)
result = graph_canvas(
    graph,
    GraphSchema(
        {
            "root": NodeType(
                "root",
                child_groups=(ChildGroup("child", "Packages", threshold=1),)
                if collect
                else (),
            ),
            "package": NodeType("package"),
        },
        {"child": EdgeType("child")},
    ),
    key="search",
    navigation_anchor="root",
    search_fields=(SearchField("count", "Count", "number"),),
    search_active_ids=("alpha", "beta", "gamma"),
    search_reorder_threshold=3,
    search_nonmatch_opacity=0.25,
    on_search_request=sent if callback else None,
)
if result.search_request:
    st.text("Requested: " + result.search_request.query)
