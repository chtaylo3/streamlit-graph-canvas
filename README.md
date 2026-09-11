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
and presentation envelopes, separate loaded-data and rendered-element budgets, an optional NetworkX
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

### Choose tree or collection display

```python
from streamlit_graph_canvas import ChildGroup, GroupDisplay, NodeType

manifest_type = NodeType(
    "manifest",
    child_groups=(
        ChildGroup(
            "depends_on",
            label="Direct dependencies",
            threshold=8,
            display=GroupDisplay.CUTOFF,
        ),
        ChildGroup(
            "resolves", label="Resolved packages", display=GroupDisplay.COLLECTION
        ),
    ),
)
```

Declare the corresponding edge types in your schema. Use `GroupDisplay.TREE`
to always show a category's children directly. Cutoffs count distinct children
**per relationship category**, grouping at the supplied number. `collapsed=False`
starts a collection expanded. Mark edges with `emphasized=True` or `optional=True`
to style them without changing their relationship type.

Collections use nested orthogonal layout and keep ELK's computed edge routes.
See [the beta contract](docs/beta-contract.md#child-display-and-edge-presentation)
for shared-child behavior and routing limits.

Graph navigation animates over 250 ms by default. Shared nodes stay on the same
canvas, entering/leaving nodes fade, and viewport changes move smoothly. Configure
`transition_ms` (0 disables motion) and `navigation_anchor` on `graph_canvas`.
The user's reduced-motion browser preference is respected automatically.

Collection display budgets count one collection node and one parent edge, plus
visible members and drawn internal edges when expanded. Hidden members remain in
the full count. `graph_canvas(max_elements=..., max_loaded_elements=...)` configures
the display and input limits separately; partial expansions show both counts.

### Local node search and optional applied ordering

Pass `search_fields=()` to enable name search, or declare scalar fields from
`Node.data`. The app owns metadata and computes descendant metrics over its full
source graph before passing them in. Search covers displayed individual nodes;
collapsed members and budget-omitted nodes are excluded. Supply
`search_active_ids` to exclude faded context by default; users can opt into
including context. Without this argument, all displayed real nodes are searched.

```python
from streamlit_graph_canvas import SearchField, graph_canvas

result = graph_canvas(
    graph,
    schema,
    key="dependencies",
    search_fields=(
        SearchField("dependency_count", "Dependencies", "number"),
        SearchField(
            "critical_below",
            "Critical findings below",
            "number",
            description="Computed by the app over all descendants",
        ),
    ),
    search_active_ids=active_node_ids,  # tuple of node IDs
    search_reorder_threshold=100,
    search_nonmatch_opacity=0.25,
)
```

Names accept comma-separated alternatives. Filters support text, numbers, declared
choices, all/any combinations, and known/unknown checks. Missing or null values are
unknown, not zero. Matches receive an outline independently of node selection;
Previous/Next/Fit matches help locate them.

Typing only previews matches and never changes their order. By default nonmatches
retain their appearance; `search_nonmatch_opacity` optionally multiplies their
opacity by a value from 0 to 1. `search_reorder_threshold` enables **Apply search**:
a collection or peer group must contain at least that many searched, displayed
nodes before its matches are ranked first. Matches retain their relative order;
context outside the search keeps its order. Layout still respects dependency
layers, so connected nodes cannot always be placed in one leftmost row. Further
edits preview a new search without changing the applied order. **Clear search**
removes highlights/dimming and restores normal layout ordering. These options can
be hard-coded or exposed by the host app.

### Search callbacks and Streamlit reruns

Local search needs no callback and sends no per-keystroke events. Only configure
`on_search_request=your_callback` if the app needs to fetch or compute additional
information. It exposes a separate **Send filters to app** button, with a visible
warning: **submitting reruns Streamlit (or the enclosing fragment)** and can repeat
database queries, expensive calculations, and rendering, causing latency or
visual disruption. Cache expensive work and avoid enabling callbacks merely to
highlight nodes. Existing camera/viewport and sprite-atlas synchronization may
still produce component events when navigating or changing layouts.

The no-argument callback runs as a Streamlit callback. After `graph_canvas`
returns on that rerun, `result.search_request` contains the validated query,
criteria, match mode, context choice, and matching node IDs. Handle app-side work
there and pass refreshed metadata into the next render. Duplicate submissions
and stale graph revisions are rejected; matching IDs describe the browser's
visible results, not a server-side query over all descendants. Recompute any
metrics or decisions from the app's authoritative data as needed.

### Fixed-box node labels

`GraphSchema.label_policy` supplies the default for every node type. A non-`None`
`NodeType.label_policy` replaces that whole policy for that type. Configure only
type policies if you prefer; other types inherit the package default. Use
`dataclasses.replace` to derive a type policy while retaining your chosen defaults.

```python
from dataclasses import replace
from streamlit_graph_canvas import GraphSchema, LabelPolicy, Node, NodeType

labels = LabelPolicy()  # path-aware, two lines, automatic ellipsis
schema = GraphSchema(
    node_types={
        "manifest": NodeType("manifest"),  # inherits labels
        "dependency": NodeType(
            "dependency",
            label_policy=replace(
                labels,
                layout="single",
                lines=1,
                ellipsis="middle",
            ),
        ),
    },
    edge_types={},
    label_policy=labels,
)
node = Node(
    "id",
    "manifest",
    "src/very/long/path/project.csproj",
    display_label="project.csproj",
)  # optional app-provided compact text
```

The default puts the directory on line one and filename on line two. Long paths
omit middle directory segments; long filenames use middle ellipsis. Labels without
a path wrap naturally, with end ellipsis on the last line. Full original labels
remain searchable and accessible even when `display_label` supplies compact text.

| Setting | Choices and compatibility |
| --- | --- |
| `layout` | `path` requires exactly 2 lines; `single` requires exactly 1; `wrap` allows 1–6. Box growth is unsupported. |
| `ellipsis` | `auto`, `end`, or `middle`. `auto` follows the default rules above; `single` uses end ellipsis. `wrap` with `middle` is rejected. |
| `font_size` | Positive integer pixels; defaults to 14. |
| `min_font_size` | `None` keeps uniform size; a positive integer no greater than `font_size` enables shrinking before truncation. Works with every layout. |
| `reveal_mode` | `delayed_hover` (default) reveals only shortened names after hovering over the name itself. `controls` retains immediate whole-node hover, keyboard-focus reveal, and the pin/copy/close button. |
| `reveal_delay_ms` | Nonnegative integer milliseconds; defaults to 600. Applies to delayed hover only. Leaving the name cancels the pending reveal. |
| `reveal_hover` | Boolean, defaults to `True`; enables the selected mode’s hover behavior. |
| `reveal_focus`, `reveal_button` | `None` uses the mode default: enabled for `controls`, disabled for `delayed_hover`. Set either to `False` to disable it in controls mode. Setting either to `True` with delayed-hover mode is incompatible and raises a configuration error. |
| `Node.display_label` | Optional display-only string; works with every policy. `Node.label` remains the full name used for search, accessibility, and copying. |

Invalid combinations raise `ValueError` when constructing the Python model, before
the component starts. Unknown options are rejected by the constructor. No label
mode grows the node or changes its geometry; app-declared node dimensions remain
authoritative. Extremely small boxes may show fewer lines than configured. Reveal
controls stay local and do not submit Streamlit events. Escape dismisses a reveal.
Copy uses the browser clipboard when available; the full label can also be selected
in the pinned reveal. Changing the global policy does not partially merge into an
explicit type policy: overrides are complete, validated policies.

The delayed-hover eligibility check uses actual rendered truncation, not label
length: wrapping or reducing the font without omitting text does not trigger a
reveal. A distinct `Node.display_label` also qualifies, so the original remains
available. Full labels remain in accessible node names in both modes.

```python
# Global default, with a custom delay:
labels = LabelPolicy(reveal_delay_ms=900)
# Opt a particular type into the previous reveal controls:
manifest_labels = replace(labels, reveal_mode="controls")
```
