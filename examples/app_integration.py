"""Run with: uv run streamlit run examples/app_integration.py."""

from dataclasses import replace

import streamlit as st
from streamlit_graph_canvas import (
    ChildGroup,
    Edge,
    EdgeStyle,
    EdgeType,
    GraphData,
    GraphSchema,
    GroupDisplay,
    LabelPolicy,
    Node,
    NodeType,
    SearchField,
    graph_canvas,
)

st.title("Application integration")
st.caption("Search previews stay local. Apply can reorder; submission is opt-in.")

labels = LabelPolicy()
schema = GraphSchema(
    node_types={
        "project": NodeType(
            "project",
            child_groups=(
                ChildGroup(
                    "uses",
                    "Dependencies",
                    threshold=12,
                    display=GroupDisplay.CUTOFF,
                    collapsed=False,
                ),
            ),
        ),
        "dependency": NodeType(
            "dependency",
            label_policy=replace(labels, layout="single", lines=1),
        ),
    },
    edge_types={"uses": EdgeType("uses", style=EdgeStyle(arrow="target"))},
    label_policy=labels,
)
dependencies = tuple(
    Node(
        f"dependency-{index}",
        "dependency",
        f"library-{index:02d}",
        # Synthetic app-computed values, not component-computed metrics.
        data={"dependency_count": index * 2, "critical_below": index % 4},
    )
    for index in range(16)
)
graph = GraphData(
    nodes=(Node("project", "project", "Example project"), *dependencies),
    edges=tuple(Edge(f"uses-{n.id}", "project", n.id, "uses") for n in dependencies),
)


def submitted() -> None:
    st.session_state["integration_submissions"] = (
        st.session_state.get("integration_submissions", 0) + 1
    )


enable_submission = st.checkbox("Enable explicit server submission", value=False)
result = graph_canvas(
    graph,
    schema,
    key="integration-canvas",
    navigation_anchor="project",
    max_elements=100,
    max_loaded_elements=1000,
    search_fields=(
        SearchField("dependency_count", "Dependencies", "number"),
        SearchField("critical_below", "Critical findings below", "number"),
    ),
    search_active_ids=tuple(n.id for n in dependencies),
    search_reorder_threshold=12,
    search_nonmatch_opacity=0.25,
    on_search_request=submitted if enable_submission else None,
)
st.write("Selected nodes", result.selected_node_ids)
st.write("Explicit submissions", st.session_state.get("integration_submissions", 0))
if result.search_request is not None:
    st.write("Submitted query", result.search_request.query)
    st.write("Displayed matches", result.search_request.matching_node_ids)
    # Recheck permissions and query authoritative data here in a real app.
