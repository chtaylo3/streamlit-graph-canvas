"""Nested geometry and controlled lifecycle contracts shared by v12 and v13."""

import streamlit as st
from streamlit_graph_canvas import (
    ChildGroup,
    Edge,
    EdgeType,
    FitView,
    GraphData,
    GraphSchema,
    Node,
    NodeStyle,
    NodeType,
    PortSide,
    PortSpec,
    graph_canvas,
)

st.session_state.setdefault("revision", 0)
if st.button("Update presentation"):
    st.session_state.revision += 1
branch_width = st.number_input("Branch width", min_value=160, value=220, step=20)
leaf_width = st.number_input("Leaf width", min_value=100, value=180, step=20)
include = st.checkbox("Include first leaf", value=True)
primary = st.checkbox("Mount primary", value=True)
duration = st.number_input(
    "Transition duration", min_value=0, max_value=1000, value=250, step=250
)
ports = (PortSpec("in", PortSide.TOP), PortSpec("out", PortSide.BOTTOM))
schema = GraphSchema(
    {
        "root": NodeType(
            "root",
            ports=ports,
            child_groups=(ChildGroup("contains", "Branches", threshold=1),),
        ),
        "branch": NodeType(
            "branch",
            NodeStyle(width=int(branch_width)),
            ports=ports,
            child_groups=(ChildGroup("contains", "Leaves", threshold=1),),
        ),
        "leaf": NodeType("leaf", NodeStyle(width=int(leaf_width)), ports=ports),
    },
    {"contains": EdgeType("contains"), "link": EdgeType("link")},
)
nodes = [Node("root", "root", f"Root {st.session_state.revision}")]
edges = []
for branch in range(2):
    bid = f"branch-{branch}"
    nodes.append(Node(bid, "branch", f"Branch {branch}"))
    edges.append(Edge(bid, "root", bid, "contains"))
    for leaf in range(2):
        lid = f"leaf-{branch}-{leaf}"
        if lid == "leaf-0-0" and not include:
            continue
        nodes.append(Node(lid, "leaf", f"Leaf {branch}.{leaf}"))
        edges.append(Edge(lid, bid, lid, "contains"))
if include:
    edges.extend(
        (
            Edge("named", "leaf-0-0", "leaf-0-1", "link", "out", "in"),
            Edge("overlap", "leaf-0-0", "leaf-0-1", "link", "out", "in"),
        )
    )
graph = GraphData(tuple(nodes), tuple(edges))


def mount(key):
    result = graph_canvas(
        graph,
        schema,
        key=key,
        fit_view=FitView.INITIAL,
        transition_ms=int(duration),
        navigation_anchor="root",
    )
    seen = st.session_state.setdefault(f"seen-{key}", [])
    for action in result.actions:
        if action.seq not in seen:
            seen.append(action.seq)
    st.markdown(
        f'<div data-testid="actions-{key}">{len(seen)}</div>', unsafe_allow_html=True
    )


if primary:
    mount("primary")
mount("secondary")
