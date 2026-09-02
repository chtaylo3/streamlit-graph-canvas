# Contributing renderer packages

Renderer distributions are trusted extensions, not data plugins. Installing a
wheel makes its static metadata discoverable; no package code is imported until
an application explicitly names that distribution in `enable_renderers()`.
Enabling a Python renderer grants it the same filesystem, network, process, and
secret access as the host Streamlit process. Review and pin renderer wheels as
carefully as any other application dependency.

## Supported contract

This development release executes `prims`, trusted `javascript`, and `raster`
transports. Graph data can never choose a distribution, module, asset, or
renderer kind that was not statically declared, hash-verified, and explicitly
enabled. JavaScript is trusted page-level code. Raster transport is available
only to a renderer with a Python PRIMS implementation. The legacy `atlas`
manifest value remains a compatibility spelling during the 0.1
release-candidate series; new manifests should declare `raster`.

Application-provided static sprites are not renderer packages. They use
`SpriteCatalog`, `SpriteBinding`, and `SpriteRef`, require no manifest or
`enable_renderers()` call, and share only the downstream atlas packing and
delivery machinery with procedural raster output.

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
demonstrates the three current transports and the legacy `atlas` compatibility
declaration.

For JavaScript, also package a Components v2 `pyproject.toml`, declare
`javascript_component` and its asset-dir-relative `javascript_entry`, and hash
the package-relative `javascript` file. Registration must use the versioned
global symbol and must be idempotent for the exact values Python supplies. See
the stock bootstrap and the JavaScript-only conformance fixture. Runtime npm
installation, dynamic import from remote origins, evaluated strings, and Blob
scripts are prohibited.

### JavaScript bootstrap authoring

Renderer bootstraps are trusted, currently hand-authored ES modules. The
repository uses several complementary checks rather than treating any one
static check as a sandbox or runtime proof:

- `uv run python -m ci.check_renderer_javascript` asks Node 24 to parse every
  JavaScript asset declared by a parseable renderer manifest in ESM mode. This
  is syntax validation only; it does not provide static typing, lint/style
  enforcement, or behavioral analysis.
- `uv run python -m ci.sync_renderer_assets --check` verifies immutable build
  identities, content-addressed filenames, hashes, and manifest/component
  agreement without changing files.
- Wheel verification validates the packaged bytes and metadata.
- The selected installed-wheel Chromium contrib set is the runtime contract
  and remains required even when all static checks pass.

Before submitting a bootstrap change, run both commands above, the frontend
Vitest suite, and the specialized `tests/e2e` contrib set that installs the
affected renderer. Intentional regeneration uses
`uv run python -m ci.sync_renderer_assets` followed by another check; it should
be reviewed like any other executable artifact change.

Raster renderer authors must emit deterministic PRIMS, use literal colors for
both theme variants, and test high-cardinality behavior under cache limits.
Static and procedural raster tiles may share immutable multi-sprite pages, but
renderer authors do not provide pages or crop coordinates. See
[`transports-and-csp.md`](transports-and-csp.md) for the atlas, tenant, and CSP
contract.

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

Conformance fixtures under `tests/e2e/fixtures/` are intentionally independent
projects rather than uv workspace members. An immediate-child fixture is
automatically discovered for compatibility-range synchronization and the full
CI fixture-wheel build, which models third-party and hostile package behavior.
Its author must still assign the distribution to a suitable contrib set.
Specialized release and compatibility workflows intentionally build only the
positive fixture needed for their scenario rather than the hostile inventory.

Before review, run:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy packages/core/src packages/contrib/src
uv build --package streamlit-graph-canvas
uv build --package streamlit-graph-canvas-contrib
uv run python -m ci.verify_wheels dist
```

The final compatibility decision comes from the clean-wheel Chromium matrix,
not from editable workspace imports.
