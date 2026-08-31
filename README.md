# Streamlit Graph Canvas

`streamlit-graph-canvas` is a domain-neutral, schema-driven graph canvas for
Streamlit. It is built on Streamlit Components v2, React Flow, and ELK.

This repository is an early implementation of the architecture in
[`docs/generalized-node-canvas-design.md`](docs/generalized-node-canvas-design.md).
The public API is not stable yet.

## Repository layout

- `packages/core`: the `streamlit-graph-canvas` distribution and frontend.
- `packages/contrib`: stock renderers built only on the core public API.
- `examples`: standalone Streamlit applications.
- `tests`: repository-level conformance tests.

## Development

Python 3.12+, uv, and Node.js 24+ are required.

```bash
uv sync
uv run pytest
uv run ruff check .

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

## Current scope

The first vertical slice provides the native graph and schema models, strict
preflight validation, explicit multigraph edge identities, versioned topology
and presentation envelopes, a combined element budget, an optional NetworkX
adapter, and a Components v2 canvas with ELK layout and persistent selection
and viewport state. Renderer discovery, PRIMS, JavaScript registration, ATLAS,
and the complete action protocol follow in later milestones.

Licensed under the Apache License, Version 2.0.

