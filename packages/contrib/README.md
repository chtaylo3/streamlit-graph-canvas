# streamlit-graph-canvas-contrib

Stock badge renderers implemented only through the public API of
`streamlit-graph-canvas`. The package currently supplies the bounded PRIMS
`streamlit-graph-canvas/contrib/count-chip` renderer.

Installing this distribution does not activate it. Applications must call
`enable_renderers(["streamlit-graph-canvas-contrib"])` and pass the returned
registry to `graph_canvas()` or `serialize_graph()`.

```python
from streamlit_graph_canvas import enable_renderers

registry = enable_renderers(["streamlit-graph-canvas-contrib"])
renderer = registry.require("streamlit-graph-canvas/contrib/count-chip", "prims")
assert renderer.distribution == "streamlit-graph-canvas-contrib"
```

The renderer accepts a bounded safe integer and an optional string `prefix`.
It is available through PRIMS, trusted JavaScript, and ATLAS transports. The
package imports only the root public API of `streamlit-graph-canvas` and ships a
static, hash-verified manifest so discovery never imports renderer code.
