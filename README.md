# Streamlit Graph Canvas

`streamlit-graph-canvas` is a domain-neutral, schema-driven graph canvas for
Streamlit. It is built on Streamlit Components v2, React Flow, and ELK.

This repository is an early implementation of the architecture in
[`docs/generalized-node-canvas-design.md`](docs/generalized-node-canvas-design.md).
The public API is not stable yet. The authoritative built/partial/deferred
status is in [`docs/beta-contract.md`](docs/beta-contract.md).

## Install

The project is currently pre-release. To run it from a checkout:

```bash
git clone https://github.com/chtaylo3/streamlit-graph-canvas.git
cd streamlit-graph-canvas
uv sync
uv run streamlit run examples/basic.py
```

Once distributions are published, install the core package and add only the
optional integrations your application uses:

```bash
pip install streamlit-graph-canvas
pip install streamlit-graph-canvas-contrib       # stock renderers
pip install "streamlit-graph-canvas[networkx]"   # NetworkX adapter
pip install "streamlit-graph-canvas[atlas]"      # PNG sprites and raster transport
```

## Quick start

```python
import streamlit as st
from streamlit_graph_canvas import (
    Edge,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    graph_canvas,
)

schema = GraphSchema(
    node_types={"service": NodeType("service")},
    edge_types={"calls": EdgeType("calls")},
)
graph = GraphData(
    nodes=(
        Node("web", "service", "Web"),
        Node("api", "service", "API"),
    ),
    edges=(Edge("web-api", "web", "api", "calls"),),
)

result = graph_canvas(graph, schema, key="service-map")
st.write("Selected nodes", result.selected_node_ids)
```

Run the fuller [`examples/basic.py`](examples/basic.py) application for styling
and palette usage.

### Static PNG sprites

Applications can map transparent PNGs to nodes without creating or enabling a
renderer. Each catalog entry requires a light image, which is also the default;
the dark image is optional and falls back deterministically to light when it is
absent.

```python
from pathlib import Path

from streamlit_graph_canvas import (
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PngImage,
    Region,
    SpriteBinding,
    SpriteCatalog,
    SpriteRef,
    StaticSprite,
    graph_canvas,
)

sprites = SpriteCatalog(
    {
        "service:healthy": StaticSprite(
            light=PngImage.from_file(Path("images/healthy-light.png")),
            dark=PngImage.from_file(Path("images/healthy-dark.png")),
        ),
        "service:warning": StaticSprite(
            light=PngImage.from_file(Path("images/warning.png")),
        ),
    }
)
schema = GraphSchema(
    node_types={
        "service": NodeType(
            "service",
            sprites=(
                SpriteBinding(
                    "thumbnail",
                    Region.at(8, 8, 72, 72),
                    layer="under",
                    fit="contain",
                ),
            ),
        )
    }
)
graph = GraphData(
    nodes=(
        Node(
            "api",
            "service",
            "API",
            sprites={
                "thumbnail": SpriteRef(
                    "service:healthy",
                    accessible_text="Healthy service",
                )
            },
        ),
    )
)

graph_canvas(graph, schema, key="service-map", sprite_catalog=sprites)
```

`PngImage.from_file()` reads the trusted server path immediately and owns its
bytes; `PngImage.from_bytes()` accepts already available PNG bytes. Neither
paths nor source bytes enter graph data or the browser envelope. Core
normalizes the images, preserves alpha, applies the binding's `contain`,
`cover`, or `fill` fit policy, and packs static and renderer-generated raster
tiles into immutable multi-sprite pages. Nodes receive real crop coordinates
for the shared page. A theme or page-delta change updates presentation only and
does not change graph topology or rerun layout.

## How it works

The current beta architecture and the `graph_canvas()` request lifecycle are
documented in [`docs/architecture.md`](docs/architecture.md). The interactive
diagrams are generated from editable Archify specifications committed beside
the rendered files.

[![Streamlit Graph Canvas architecture](docs/diagrams/system-architecture.svg)](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/system-architecture.html)

Select the diagram to open the interactive GitHub Pages version.

## Documentation

- [Architecture and public API](docs/architecture.md)
- [Beta contract and implementation status](docs/beta-contract.md)
- [Renderer authoring](docs/contributing-renderers.md)
- [JavaScript, raster and sprite delivery, multi-tenancy, and CSP](docs/transports-and-csp.md)
- [Conformance testing](docs/conformance-testing.md)
- [Dependency lifecycle](docs/dependency-lifecycle.md)
- [Build and release process](docs/release-process.md)
- [Release activation](docs/release-activation.md)
- [Long-term design](docs/generalized-node-canvas-design.md)

## Repository layout

- `packages/core`: the `streamlit-graph-canvas` distribution and frontend.
- `packages/contrib`: stock renderers built only on the core public API.
- `examples`: standalone Streamlit applications.
- `tests`: repository-level tests, including the clean-wheel Streamlit and
  Playwright/Chromium conformance suite under `tests/e2e`.
- `ci`: contrib-set selection and release-wheel policy checks.

## Development

The supported Python compatibility lanes cover Python 3.12 through 3.14. uv is
used for Python development, and Node.js 24.x is the supported frontend build
toolchain.

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy packages/core/src packages/contrib/src

cd packages/core/src/streamlit_graph_canvas/frontend
npm install
npm test
npm run build
```

Run the example after building the frontend:

```bash
uv run streamlit run examples/basic.py
```

Build each distribution independently:

```bash
uv build --package streamlit-graph-canvas
uv build --package streamlit-graph-canvas-contrib
```

Renderer authors should start with
[`docs/contributing-renderers.md`](docs/contributing-renderers.md). The combined
browser gate and local commands are described in
[`docs/conformance-testing.md`](docs/conformance-testing.md).
Dependency support, minimum/latest/forward CI lanes, and update governance are
documented in [`docs/dependency-lifecycle.md`](docs/dependency-lifecycle.md).

## Current scope

The current vertical slice provides the native graph and schema models, strict
preflight validation, explicit multigraph edge identities, versioned topology
and presentation envelopes, a combined element budget, an optional NetworkX
adapter, and a Components v2 canvas with ELK layout, declarative styles and
ports, persistent selection and viewport state, and a validated click-action
protocol. It also provides import-free static renderer discovery, explicit
enablement, and bounded PRIMS and raster transports demonstrated by the stock
count-chip renderer. Static transparent PNG catalogs use separate sprite
bindings and do not require renderer enablement. Static and procedural rasters
share deterministic immutable atlas pages, real crop coordinates, bounded
session/tenant caches, and Blob-backed browser delivery. Trusted JavaScript
registration and the image paths are covered by CSP checks. Additional action
gestures remain later milestones and fail closed in this release. Transport
security, multi-tenant configuration, and deployment policy are documented in
[`docs/transports-and-csp.md`](docs/transports-and-csp.md).

Licensed under the Apache License, Version 2.0.
