# Contributing renderer packages

Renderer distributions are trusted extensions, not data plugins. Installing a
wheel makes its static metadata discoverable; no package code is imported until
an application explicitly names that distribution in `enable_renderers()`.
Enabling a Python renderer grants it the same filesystem, network, process, and
secret access as the host Streamlit process. Review and pin renderer wheels as
carefully as any other application dependency.

## Supported contract

This development release executes only the `prims` transport. JavaScript and
ATLAS declarations are parsed for forward compatibility but serialization
fails closed until their trusted bootstrap and bounded-cache implementations
land. Graph data can never choose a distribution, module, asset, or renderer
kind that was not statically declared and explicitly enabled.

A package must:

- publish a wheel with exactly one `renderer.toml` inside its import package;
- advertise through `streamlit_graph_canvas.renderers` entry points;
- use globally namespaced kinds in `vendor/package/kind` form;
- declare a PEP 440 renderer API range and a version matching wheel metadata;
- place every public asset below the manifest and record its lowercase SHA256;
- depend on a bounded compatible core range;
- import contrib-facing types only from `streamlit_graph_canvas`'s public API;
- avoid source maps, credentials, private data, and development dependencies in
  release wheels.

The stock manifest in
[`packages/contrib/src/streamlit_graph_canvas_contrib/renderer.toml`](../packages/contrib/src/streamlit_graph_canvas_contrib/renderer.toml)
is the minimal PRIMS example.

## PRIMS safety boundary

A PRIMS renderer returns only `RectPrim`, `CirclePrim`, and `TextPrim`. Core
rejects raw dictionaries, HTML, scripts, unknown palette tones, non-finite or
negative geometry, text over 1,024 characters, and output over 200 primitives
per badge. React creates fixed SVG elements and inserts text as text content.
Renderer exceptions are converted to stable `SGC_RENDERER_EXECUTION`
diagnostics; they do not silently remove a badge.

Graph and badge inputs must be JSON-compatible, at most 20 levels deep, contain
only finite numbers, JavaScript-safe integers, and string mapping keys, and fit
the core's serialized-data budget. Badge regions are fixed in the schema, so
instance data cannot change node geometry or trigger layout.

These checks limit malformed output and browser injection. They are not a
sandbox for malicious Python. Do not enable untrusted distributions.

## Required tests

Each renderer needs unit tests for valid output, every supported option, invalid
data, boundary sizes, and deterministic output. It must also appear in at least
one set in [`ci/contrib-sets.toml`](../ci/contrib-sets.toml); CI rejects renderer
packages omitted from all sets.

Before review, run:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy packages/core/src packages/contrib/src
uv build --package streamlit-graph-canvas
uv build --package streamlit-graph-canvas-contrib
uv run python ci/verify_wheels.py dist
```

The final compatibility decision comes from the clean-wheel Chromium matrix,
not from editable workspace imports.
