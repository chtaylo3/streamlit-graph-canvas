# Architecture and public API

This page describes the implementation in the current beta. It is a concise
map for application authors and contributors; the
[beta contract](beta-contract.md) remains authoritative for what is built,
partial, or deferred. The [long-term design](generalized-node-canvas-design.md)
contains rationale and future milestones and should not be read as current API
documentation.

## System architecture

[![Streamlit Graph Canvas system architecture](diagrams/system-architecture.svg)](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/system-architecture.html)

Open the [interactive system architecture diagram](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/system-architecture.html).
Its editable source is
[`system-architecture.json`](diagrams/system-architecture.json).

The application constructs domain-neutral `GraphData` and `GraphSchema`
objects and calls `graph_canvas(graph, schema, key=...)`. It may also pass a
`SpriteCatalog` containing named, static PNGs. Core validates the graph,
element and JSON budgets, styles, actions, static image bounds, and any
explicitly enabled renderer metadata before serializing a versioned component
envelope.

The envelope crosses the Streamlit Components v2 boundary to the React Flow
frontend. ELK computes positions when topology changes; presentation-only
changes preserve layout. Selection, viewport, validated click actions, theme,
resolution, and atlas-page browser state return to Python and are reconciled
across Streamlit reruns.

Renderer packages are inert until explicitly enabled. The three renderer
transports are:

- `PRIMS`: Python renderers emit a bounded rectangle, circle, and text
  vocabulary that the browser paints as SVG.
- `JavaScript`: reviewed wheels provide hash-bound, same-origin bootstrap code
  that registers trusted scoped-SVG factories in the application page.
- `RASTER`: core rasterizes PRIMS with Pillow, then sends the tile through the
  shared atlas packing and delivery layer. The legacy `ATLAS` name remains a
  compatibility spelling for the 0.1 release-candidate series.

Static sprites are a separate image source, not a renderer transport. A
`SpriteBinding` declares a fixed paint region and `contain`, `cover`, or `fill`
policy. Each `SpriteRef` names an entry in the explicitly supplied
`SpriteCatalog`; it never names a file or contains image bytes. A required
light/default PNG and optional dark PNG are normalized into RGBA tiles. Dark
mode selects the dark image when present and otherwise falls back to light.
Static sprites therefore do not require renderer discovery or
`enable_renderers()`.

Both static sprites and procedural raster output converge on the same
deterministic atlas layer. Missing tiles are packed into immutable pages, page
deltas are content addressed, and each resolved node layer carries the actual
physical crop coordinates. The browser validates the page and rectangle,
creates a shared Blob URL, and crops the requested sprite into the binding's
logical region. Theme, resolution, and atlas-page changes affect presentation
identity but never topology identity or ELK layout.

The trust model and deployment requirements are detailed in
[JavaScript, raster and sprite delivery, multi-tenancy, and
CSP](transports-and-csp.md).

## Request lifecycle

[![graph_canvas request lifecycle](diagrams/request-lifecycle.svg)](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/request-lifecycle.html)

Open the [interactive request lifecycle diagram](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/request-lifecycle.html).
Its editable source is
[`request-lifecycle.json`](diagrams/request-lifecycle.json).

`graph_canvas()` validates and serializes before mounting the canvas. When a
trusted JavaScript renderer is enabled, its bootstrap mounts before the core
component. The frontend lays out new topology, restores interaction state, and
returns changes through `CanvasResult`; configured callbacks cause the normal
Streamlit rerun cycle.

## Public API map

Import supported names from `streamlit_graph_canvas`; package submodules are
implementation details.

| Task | Primary public API |
| --- | --- |
| Define a graph | `GraphData`, `Node`, `Edge` |
| Define its schema and appearance | `GraphSchema`, `NodeType`, `EdgeType`, `NodeStyle`, `EdgeStyle`, `PaletteTone`, `PortSpec`, `Region`, `BadgeBinding`, `SpriteBinding` |
| Convert NetworkX data | `from_networkx` from the `networkx` extra |
| Validate or serialize without mounting | `validate`, `serialize_graph`, `SerializedGraph` |
| Render in Streamlit | `graph_canvas`, `CanvasResult`, `SelectionMode`, `FitView` |
| Handle returned interactions | `CanvasAction`, `ActionModifiers`, `CanvasViewport` |
| Discover and enable renderers | `discover_renderer_manifests`, `discover_renderer_diagnostics`, `enable_renderers`, `RendererRegistry` |
| Author a PRIMS renderer | `BadgeRenderer`, `BadgeContext`, `RectPrim`, `CirclePrim`, `TextPrim`, `validate_primitives` |
| Supply static PNG sprites | `PngImage`, `StaticSprite`, `SpriteCatalog`, `SpriteRef` from the `atlas` extra |
| Configure raster and atlas delivery | `Transport.RASTER`, `AtlasPolicy`, `AtlasScope`, `AtlasPageCache` (`AtlasCache` compatibility alias) from the `atlas` extra |
| Build host CSP policy | `required_csp_directives`, `format_csp`, `streamlit_host_csp` |

Renderer authors should continue with
[Contributing renderers](contributing-renderers.md). Application deployers using
JavaScript, raster transport, or static sprites should review the CSP guide
before deployment.

## Diagram maintenance

The JSON files in `docs/diagrams` are the source of truth for these diagrams.
Regenerate and validate their HTML with Archify whenever a package boundary,
transport, or request-lifecycle fact changes. Review diagram changes alongside
the corresponding implementation and beta-contract updates.
