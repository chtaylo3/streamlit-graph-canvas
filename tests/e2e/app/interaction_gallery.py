"""Selection modes, user-visible errors, large graphs, and telemetry."""

import streamlit as st
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    FitView,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    SearchField,
    SelectionMode,
    ValidationError,
    graph_canvas,
)

st.title("Interaction Gallery")
mode = st.radio("Selection mode", ["single", "multiple", "none"], horizontal=True)
disable_worker = st.checkbox("Disable worker")
invalid = st.checkbox("Invalid graph")
large = st.checkbox("Large graph")
telemetry = st.checkbox("Telemetry")
hidden = st.checkbox("Hide canvas")

schema = GraphSchema(
    {"service": NodeType("service"), "store": NodeType("store")},
    {"calls": EdgeType("calls")},
)
if large:
    # 350 nodes + 349 edges stays just inside the default 700-element budget.
    count = 350
    graph = GraphData(
        tuple(Node(f"n{i}", "service", f"Node {i}") for i in range(count)),
        tuple(
            Edge(f"e{i}", f"n{(i - 1) // 2}", f"n{i}", "calls") for i in range(1, count)
        ),
    )
else:
    graph = GraphData(
        (
            Node("api", "service", "API", data={"tier": 1}),
            Node(
                "worker", "service", "Worker", data={"tier": 2}, disabled=disable_worker
            ),
            Node("db", "store", "Database", data={"tier": 3}),
        ),
        (
            Edge("api-worker", "api", "worker", "calls"),
            Edge("worker-db", "worker", "db", "calls"),
            *((Edge("dangling", "api", "missing", "calls"),) if invalid else ()),
        ),
    )

st.session_state.actions = st.session_state.get("actions", 0)
if not hidden:
    try:
        result = graph_canvas(
            graph,
            schema,
            key=f"interaction-{mode}",
            selection=SelectionMode(mode),
            fit_view=FitView.INITIAL,
            search_fields=(SearchField("tier", "Tier", "number"),),
            telemetry_endpoint=(
                "http://127.0.0.1:8520/sgc-telemetry" if telemetry else None
            ),
            height=480,
        )
    except ValidationError as error:
        # Apps surface diagnostics; the canvas must not mount half-validated.
        st.exception(error)
    else:
        st.session_state.actions += len(result.actions)
        st.text(f"Selected: {','.join(result.selected_node_ids) or '-'}")
        st.text(f"Actions: {st.session_state.actions}")
        if result.actions:
            last = result.actions[-1]
            st.text(
                f"Last: {last.node_id} shift={last.modifiers.shift} "
                f"meta={last.modifiers.meta} alt={last.modifiers.alt}"
            )
