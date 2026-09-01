# Architecture and public API

This page describes the implementation in the current beta. It is a concise
map for application authors and contributors; the
[beta contract](beta-contract.md) remains authoritative for what is built,
partial, or deferred. The [long-term design](generalized-node-canvas-design.md)
contains rationale and future milestones and should not be read as current API
documentation.

## System architecture

[![Streamlit Graph Canvas system architecture](diagrams/system-architecture.svg)](diagrams/system-architecture.html)

Open the [interactive system architecture diagram](diagrams/system-architecture.html).
Its editable source is
[`system-architecture.json`](diagrams/system-architecture.json).

The application constructs domain-neutral `GraphData` and `GraphSchema`
objects and calls `graph_canvas(graph, schema, key=...)`. Core validates the
graph, element and JSON budgets, styles, actions, and any explicitly enabled
renderer metadata before serializing a versioned component envelope.

The envelope crosses the Streamlit Components v2 boundary to the React Flow
frontend. ELK computes positions when topology changes; presentation-only
changes preserve layout. Selection, viewport, validated click actions, and
ATLAS browser state return to Python and are reconciled across Streamlit
reruns.

Renderer packages are inert until explicitly enabled. The three current
transports are:

- `PRIMS`: Python renderers emit a bounded rectangle, circle, and text
  vocabulary that the browser paints as SVG.
- `JavaScript`: reviewed wheels provide hash-bound, same-origin bootstrap code
  that registers trusted scoped-SVG factories in the application page.
- `ATLAS`: core rasterizes PRIMS with Pillow and sends content-addressed,
  bounded PNG page deltas for session- or tenant-scoped caches.

The trust model and deployment requirements are detailed in
[JavaScript, ATLAS, multi-tenancy, and CSP](transports-and-csp.md).

## Request lifecycle

[![graph_canvas request lifecycle](diagrams/request-lifecycle.svg)](diagrams/request-lifecycle.html)

Open the [interactive request lifecycle diagram](diagrams/request-lifecycle.html).
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
| Define its schema and appearance | `GraphSchema`, `NodeType`, `EdgeType`, `NodeStyle`, `EdgeStyle`, `PaletteTone`, `PortSpec`, `Region`, `BadgeBinding` |
| Convert NetworkX data | `from_networkx` from the `networkx` extra |
| Validate or serialize without mounting | `validate`, `serialize_graph`, `SerializedGraph` |
| Render in Streamlit | `graph_canvas`, `CanvasResult`, `SelectionMode`, `FitView` |
| Handle returned interactions | `CanvasAction`, `ActionModifiers`, `CanvasViewport` |
| Discover and enable renderers | `discover_renderer_manifests`, `discover_renderer_diagnostics`, `enable_renderers`, `RendererRegistry` |
| Author a PRIMS renderer | `BadgeRenderer`, `BadgeContext`, `RectPrim`, `CirclePrim`, `TextPrim`, `validate_primitives` |
| Configure ATLAS | `AtlasPolicy`, `AtlasScope`, `AtlasCache` from the `atlas` extra |
| Build host CSP policy | `required_csp_directives`, `format_csp`, `streamlit_host_csp` |

Renderer authors should continue with
[Contributing renderers](contributing-renderers.md). Application deployers using
JavaScript or ATLAS should review the CSP guide before enabling either
transport.

## Diagram maintenance

The JSON files in `docs/diagrams` are the source of truth for these diagrams.
Regenerate and validate their HTML with Archify whenever a package boundary,
transport, or request-lifecycle fact changes. Review diagram changes alongside
the corresponding implementation and beta-contract updates.
