# streamlit-graph-canvas

A domain-neutral, schema-driven graph canvas for Streamlit. The core package
owns validated graph models, deterministic ELK layout, bounded serialization,
the Streamlit Components v2 bridge, explicit PRIMS, JavaScript, and raster
renderer transports, and static PNG sprite delivery through bounded atlas
pages.

```python
from streamlit_graph_canvas import (
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    validate,
)

schema = GraphSchema(
    node_types={"service": NodeType("service")},
    edge_types={"calls": EdgeType("calls")},
)
graph = GraphData(nodes=(Node("api", "service", "API"),), edges=())
validate(schema, graph)
```

Applications render with `graph_canvas(graph, schema, key="graph")`; graph is
the first positional argument and schema is the second. Optional renderer
packages are inert until explicitly passed through `enable_renderers()`.

Static sprites do not use renderer packages or `enable_renderers()`. Construct
a `SpriteCatalog` of `StaticSprite` entries, declare a `SpriteBinding` on the
node type, assign a `SpriteRef` to a node, and pass `sprite_catalog=` to
`graph_canvas()`. The light PNG is required and is the default; a dark PNG is
optional, with deterministic dark-to-light fallback. `PngImage.from_file()`
and `PngImage.from_bytes()` keep paths and source bytes on the server. Core
preserves alpha, supports `contain`, `cover`, and `fill`, and packs static and
procedural raster tiles into immutable multi-sprite pages whose real crop
coordinates are sent with each resolved node layer.

The supported Python surface is exported from `streamlit_graph_canvas`;
package submodules are implementation details. See the project documentation
for the static-sprite quick start, wire protocol, CSP, dependency, and beta
compatibility contracts.

The compatibility matrix tests Python 3.12 through 3.14. Node.js 24.x is used
to build the packaged frontend and is not required when running an installed
wheel.
