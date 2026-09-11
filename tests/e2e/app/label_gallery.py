import streamlit as st
from streamlit_graph_canvas import (
    GraphData,
    GraphSchema,
    LabelPolicy,
    Node,
    NodeStyle,
    NodeType,
    graph_canvas,
)

st.session_state.runs = st.session_state.get("runs", 0) + 1
st.text(f"Runs: {st.session_state.runs}")
delay = st.number_input("Reveal delay", min_value=0, value=600)
font_size = st.number_input("Label font size", min_value=1, value=14)
node_width = st.number_input("Node width", min_value=100, value=180)
graph_canvas(
    GraphData(
        (
            Node("path", "path", "src/integrations/prefect/infra/packages-lock.json"),
            Node("single", "single", "a-very-long-original-manifest-filename.csproj"),
            Node(
                "compact",
                "path",
                "original/full-searchable-name.csproj",
                display_label="short.csproj",
            ),
            Node("short", "delayed", "tiny"),
            Node(
                "delayed",
                "delayed",
                "very/long/directory/another/long/file-name.csproj",
            ),
            Node(
                "alias", "delayed", "full/original/name.csproj", display_label="alias"
            ),
            Node("shrink", "shrink", "abcdefghijklmno"),
        ),
        (),
    ),
    GraphSchema(
        {
            "delayed": NodeType(
                "delayed", label_policy=LabelPolicy(reveal_delay_ms=1000)
            ),
            "path": NodeType("path", NodeStyle(width=int(node_width))),
            "single": NodeType(
                "single",
                label_policy=LabelPolicy(
                    layout="single",
                    lines=1,
                    ellipsis="middle",
                    reveal_hover=False,
                    reveal_focus=False,
                    reveal_button=False,
                ),
            ),
            "shrink": NodeType(
                "shrink",
                NodeStyle(width=100),
                label_policy=LabelPolicy(layout="single", lines=1, min_font_size=8),
            ),
        },
        {},
        label_policy=LabelPolicy(
            reveal_mode="controls", reveal_delay_ms=int(delay), font_size=int(font_size)
        ),
    ),
    key="labels",
    search_fields=(),
)
