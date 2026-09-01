# streamlit-graph-canvas

A domain-neutral, schema-driven graph canvas for Streamlit. The core package
owns validated graph models, deterministic ELK layout, bounded serialization,
the Streamlit Components v2 bridge, and explicit PRIMS, JavaScript, and ATLAS
renderer transports.

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

Applications render with `graph_canvas(graph, schema, key="graph")`. Optional renderer
packages are inert until explicitly passed through `enable_renderers()`. The
supported Python surface is exported from `streamlit_graph_canvas`; package
submodules are implementation details. See the project documentation for the
wire-protocol, CSP, dependency, and beta compatibility contracts.
