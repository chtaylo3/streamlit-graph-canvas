# Architecture and public API

This page describes the implementation in the 0.1 release-candidate series.
It is a concise map for application authors and contributors; the
[beta contract](beta-contract.md) remains authoritative for what is built,
partial, or deferred. The [long-term design](generalized-node-canvas-design.md)
contains rationale and proposed milestones; it does not define the current API.

To integrate the component, use the [app developer guide](app-developer-guide.md)
for ownership boundaries, a runnable example, configuration defaults, and diagnostics.

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
frontend. A separate `layoutHash` covers node geometry, ports, relationships,
and collection rules. ELK runs when those inputs, local grouping, or order change;
label policies, colors, and collection titles refresh without laying out again.
The existing `topologyHash` remains the action-protocol identity and still
includes schema changes. Selection, viewport, validated click actions, theme,
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
light or default PNG and optional dark PNG are normalized into RGBA tiles. Dark
mode selects the dark image when present and otherwise falls back to light.
Static sprites therefore do not require renderer discovery or
`enable_renderers()`.

Both static sprites and procedural raster output converge on the same
deterministic atlas layer. Equal atlas policies share a process-wide cache;
page and byte limits apply per distinct policy, with no aggregate ceiling across
policies. Missing tiles are packed into immutable pages, page deltas are content
addressed, and each resolved node layer carries the actual
physical crop coordinates. The browser validates the page and rectangle,
creates a shared Blob URL, and crops the requested sprite into the binding's
logical region. Theme, resolution, and atlas-page changes affect presentation
identity but never topology identity or ELK layout.

The trust model and deployment requirements are detailed in the
[transport, cache, and Content Security Policy (CSP) guide](transports-and-csp.md).

## Request lifecycle

[![graph_canvas request lifecycle](diagrams/request-lifecycle.svg)](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/request-lifecycle.html)

Open the [interactive request lifecycle diagram](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/request-lifecycle.html).
Its editable source is
[`request-lifecycle.json`](diagrams/request-lifecycle.json).

`graph_canvas()` validates and serializes before mounting the canvas. When a
trusted JavaScript renderer is enabled, its bootstrap mounts before the core
component. The frontend lays out changed geometry or grouping, restores
interaction state, and returns changes through `CanvasResult`; configured callbacks cause the normal
Streamlit rerun cycle.

Collection visibility uses an adjacency traversal of the loaded graph before
applying the rendered-element budget. Search state and evaluation live in
`use-node-search.ts`: metadata, rendered membership, and filters invalidate the
results; geometry-only animation frames reuse them. Exiting and hidden nodes
are excluded. Search is browser-local unless the application explicitly enables
submission callbacks, which cause Streamlit reruns.

React Flow measurements are retained after animation and search styling replace
controlled node objects, preserving handle bounds and connectors across rerenders.
Navigation anchors keep shared ancestors and sibling context stable; changed
layouts still animate. Full-label overlays close when the canvas moves or the
page scrolls.

The frontend's `npm run format` and `npm run format:check` cover the grouping,
canvas, label, search, and telemetry modules. The build checks that formatting;
other modules can be adopted as they are changed.

## Public API map

Import supported names from `streamlit_graph_canvas`; package submodules are
implementation details.

| Task | Primary public API |
| --- | --- |
| Define a graph | `GraphData`, `Node`, `Edge` |
| Define its schema and appearance | `GraphSchema`, `NodeType`, `EdgeType`, `NodeStyle`, `EdgeStyle`, `PaletteTone`, `PortSpec`, `Region`, `BadgeBinding`, `SpriteBinding` |
| Configure collections | `ChildGroup`, per-category display mode and cutoff |
| Show sibling context | `add_sibling_context`, anchor selection and opacity |
| Configure fixed-box names | `LabelPolicy`, schema defaults and per-type overrides |
| Search visible nodes | `SearchField`, `SearchCriterion`, `SearchRequest`, and `graph_canvas` search options |
| Convert NetworkX data | `from_networkx` from the `networkx` extra |
| Validate or serialize without mounting | `validate`, `serialize_graph`, `SerializedGraph` |
| Render in Streamlit | `graph_canvas`, `CanvasResult`, `SelectionMode`, `FitView` |
| Handle returned interactions | `CanvasAction`, `ActionModifiers`, `CanvasViewport` |
| Discover and enable renderers | `discover_renderer_manifests`, `discover_renderer_diagnostics`, `enable_renderers`, `RendererRegistry` |
| Author a PRIMS renderer | `BadgeRenderer`, `BadgeContext`, `RectPrim`, `CirclePrim`, `TextPrim`, `validate_primitives` |
| Supply static PNG sprites | `PngImage`, `StaticSprite`, `SpriteCatalog`, `SpriteRef` from the `atlas` extra |
| Configure raster and atlas delivery | `Transport.RASTER`, `AtlasPolicy`, `AtlasPageCache` (`AtlasCache` compatibility alias) from the `atlas` extra |
| Build host CSP policy | `required_csp_directives`, `format_csp`, `streamlit_host_csp` |

To create a renderer, follow the
[renderer contribution guide](contributing-renderers.md). Before deploying
JavaScript renderers, raster transport, or static sprites, review the
[CSP guide](transports-and-csp.md).

<a id="diagram-maintenance"></a>

## Maintain the diagrams

The JSON files in `docs/diagrams` are the source of truth for these diagrams.
Regenerate and validate their HTML with Archify whenever a package boundary,
transport, or request-lifecycle fact changes. Review diagram changes alongside
the corresponding implementation and beta-contract updates.

## Application interaction boundary

[![App and canvas interaction contract](diagrams/app-interactions.svg)](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/app-interactions.html)

This sequence separates browser-local query preview and **Apply search** ordering from
explicit app submission. Viewport and atlas synchronization may still emit
component events; local search does not mean every canvas interaction avoids
a Streamlit rerun. The [editable source](diagrams/app-interactions.json) and
[app-developer guide](app-developer-guide.md#search-locally-submit-only-when-needed)
document the contract.

## Documentation style

Follow the [Google developer documentation style guide](https://developers.google.com/style)
when editing documentation, examples, and authored diagram text. Use sentence-case
headings, imperative verbs for tasks, active voice, American English, and serial
commas. Format code identifiers as code and UI labels in bold. Give links
descriptive text and images meaningful alternative text.

Keep proposals and historical plans clearly labeled. Preserve public identifiers,
code behavior, and existing heading anchors when making editorial changes. Edit
the dependency matrix generator and diagram JSON sources, then regenerate their
outputs; do not edit generated HTML or SVG by hand.
