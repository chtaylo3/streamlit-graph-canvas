# streamlit-graph-canvas-contrib

Stock badge renderers implemented only through the public API of
`streamlit-graph-canvas`. The package currently supplies the bounded PRIMS
`streamlit-graph-canvas/contrib/count-chip` renderer.

Installing this distribution does not activate it. Applications must call
`enable_renderers(["streamlit-graph-canvas-contrib"])` and pass the returned
registry to `graph_canvas()` or `serialize_graph()`.
