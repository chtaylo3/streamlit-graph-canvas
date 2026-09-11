---
title: App developer guide
---

# Build an application with Graph Canvas

Start here if you are embedding the reusable component in a Streamlit app.
This guide describes the repository's current API. Use the documentation from
the same tag as your installed package: the collection, search, and label work
merged in #21 targets rc2 and is not the older rc1 API. Until rc2 is published,
use a wheel built from this checkout for those features.

## Install and run

Python 3.12–3.14 and Streamlit 1.62 or later are supported by the compatibility
matrix. Install a published prerelease with
`pip install --pre streamlit-graph-canvas`, or use the checkout for the current
development API:

```bash
uv sync --locked
uv run streamlit run examples/app_integration.py
```

The wheel includes its frontend. Application users do not need Node.js or an
ELK service. Node.js 24 is needed only to build or modify the frontend.

| Need | Install or configure |
| --- | --- |
| Nodes, edges, collections, labels, search | Core package only |
| NetworkX conversion | `streamlit-graph-canvas[networkx]` |
| Static PNGs or procedural raster images | `streamlit-graph-canvas[atlas]` |
| Stock badge renderers | Matching `streamlit-graph-canvas-contrib`; explicitly enable renderers |
| Server metrics | `streamlit-graph-canvas[otel]`; app supplies the SDK/provider |
| Browser metrics | Explicit `telemetry_endpoint`; collector and CSP configured by app |

Pin compatible core/contrib versions in your lockfile. A locally rebuilt wheel
with the same version should have a distinct path/hash so installation cannot
silently reuse an older artifact. See the [release process](release-process.md).

## Decide what the application owns

| Application responsibility | Component responsibility |
| --- | --- |
| Fetching data, authorization, filtering what may be sent to the browser | Validating the supplied graph and schema |
| Stable node/edge IDs, relationship meanings, domain labels | Rendering a directed multigraph and preserving interaction state |
| Selecting the visible hierarchy and when to load more data | Grouping the supplied children and enforcing display limits |
| Computing direct/transitive counts, vulnerabilities, other metadata | Searching configured scalar fields on displayed nodes |
| Choosing which settings to expose to users | Applying declared grouping, label, transition and search policies |
| Handling validated results and performing server-side work | Local interaction, layout, transitions and returned component state |

The component has no repository, manifest, package, or vulnerability concepts.
It does not fetch descendants or calculate transitive metrics. Collapsing a
collection hides already supplied data; it is not lazy loading, pagination, or
an authorization boundary. Do not put secrets in `Node.data`: metadata is sent
to the browser even when the corresponding node is not currently visible.

## Model the graph and preserve identity

Use the exported `GraphData`, `Node`, `Edge`, and `GraphSchema` classes. Import
from `streamlit_graph_canvas`, not its internal modules. Every node and edge
needs a stable, unique ID; parallel relationships have separate edge IDs.
Declare node/edge types and ensure every edge references supplied endpoints
and valid ports. Keep the same `graph_canvas(..., key="...")` key across reruns;
use distinct keys for separate canvases.

Use `Node.label` for the full name and `display_label` only for a compact
display alias. Put scalar search values in `Node.data`; required badge bindings
instead need matching entries in `Node.badges`. An edge's `type` describes its
relationship; `emphasized`, `optional`, `opacity`, and schema styles describe
presentation. Use `EdgeStyle.arrow` to communicate the app's chosen direction
(`none`, `source`, `target`, or `both`).

You can validate without mounting using `validate(schema, graph)`. Note that
rendering uses the opposite argument order: `graph_canvas(graph, schema, ...)`.
The [runnable integration example](../examples/app_integration.py) combines
stable IDs, category grouping, metadata search, label policies, and results.

## Choose disclosure and budgets explicitly

Attach `ChildGroup` declarations to the **parent** `NodeType`, keyed by outgoing
edge type. Each category independently supports `GroupDisplay.TREE`,
`COLLECTION`, or `CUTOFF`. A cutoff groups at `count >= threshold`; it counts
distinct children in that category, not all children of all types. The package
does not impose the example app's cutoff of 12. `collapsed` controls the initial
state separately from the display mode.

| Limit | Meaning | Default |
| --- | --- | --- |
| `graph_canvas(max_loaded_elements=...)` | Supplied nodes plus edges, before grouping | Greater of 20,000 and `max_elements` |
| `graph_canvas(max_elements=...)` | Rendered nodes and edges after grouping | 700 |
| Direct `validate` / `serialize_graph` element limit | Input graph size, not rendered collection size | 700 |

Element counts do not replace JSON-data and image-size validation. Arbitrary
Python objects, non-finite numbers, and oversized payloads are rejected; keep
metadata compact and JSON-compatible.

A collapsed collection normally costs one container node and one parent edge.
For an expanded collection of 100 independent members, that is 102 elements
before other context or internal relationships. Parent-to-member links replaced
by the collection are not charged again; actual drawn internal edges still
count. Partial expansion preserves the loaded membership count. Budget-omitted
nodes and intentionally collapsed members are different conditions.

Shared children can stay outside competing expanded groups, and dense or cyclic
graphs can require fallback routes. Orthogonal routing does not guarantee a
globally shortest route or zero crossings for every graph. See the
[grouping contract](beta-contract.md#child-display-and-edge-presentation).

The app decides whether navigating to a parent supplies only its immediate
children or more descendants. Supplying deeper nodes and expecting grouping
alone to enforce domain-level disclosure is not a substitute for that decision.

## Navigate with stable context

Build the focused view in your app. Optionally call
`add_sibling_context(visible, available, anchor_id, enabled=True, opacity=0.2,
max_elements=...)` before rendering. It adds same-type siblings and their parent
links when their parents are already visible and there is room. It does not
expand those siblings. Its budget counts the supplied nodes/edges; the later
rendered budget remains a separate stage.

Store user settings by node type in your own `st.session_state` if they should
survive moving up, down, or across the hierarchy. The helper does not own that
UI or persistence. Pass an appropriate shared `navigation_anchor` to
`graph_canvas` to preserve visual context. Motion defaults to 250 ms;
`transition_ms=0` disables it, and reduced-motion preferences are respected.
The component owns layout positions; caller-specified coordinates are not a
supported positioning API.

## Search locally; submit only when needed

[![App and canvas interaction contract](diagrams/app-interactions.svg)](https://chtaylo3.github.io/streamlit-graph-canvas/diagrams/app-interactions.html)

Pass `search_fields=()` for name search, or supply `SearchField` entries for
text, number, and choice keys in `Node.data`. Compute descendant metrics from
your authoritative source graph before rendering. Missing/null values mean
unknown, not zero. Search does not recursively fetch or inspect hidden descendants.

Set `search_active_ids` to the active, non-context node IDs when faded siblings
should be excluded by default. Opacity alone does not exclude a node from
search. Without an explicit scope, all displayed real nodes participate;
collapsed members and budget-omitted nodes do not. Users may opt into context.

Typing highlights matches without reordering. `search_nonmatch_opacity` can dim
nonmatches. `search_reorder_threshold` enables explicit **Apply search** for
eligible collection/peer groups; ranking respects dependency layers, so it does
not force every match into one leftmost row. **Clear search** restores normal
ordering. Search matching and selection are separate states.

| Interaction | Streamlit boundary |
| --- | --- |
| Type/filter search; reveal/copy a label | Local; no per-keystroke search callback |
| Apply/Clear search or expand a collection | Browser presentation/layout; viewport or atlas synchronization may still emit events |
| Selection, node click, committed viewport | Component state/events; registered callbacks run through Streamlit |
| **Send filters to app** | Explicit opt-in search submission; triggers a Streamlit or fragment rerun |

`on_search_request` is a **no-argument Streamlit callback**, not a function
receiving each typed character. After the component returns on the rerun, read
`result.search_request` (`SearchRequest`). It includes query, criteria,
all/any mode, context choice, matching IDs, and sequence. Cache expensive data
loads and compute updated metadata before the next render. A submission can
repeat queries, computation, and rendering; do not enable it just for highlighting.

`CanvasResult` also returns `selected_node_ids`, `viewport`, `actions`, and
topology/presentation hashes. Click actions are validated and acknowledged;
stale revisions and duplicates are discarded. Only node-click actions are in
protocol v1; collection toggles are not expand/collapse domain callbacks.
Treat browser matching IDs as display results, not permission to perform an
operation: re-check authorization against the server's source data.

## Fit names without changing node geometry

`GraphSchema.label_policy` sets a global `LabelPolicy`; a type override replaces
the **entire** policy. Use `dataclasses.replace` when deriving an override.
The default is path-aware two-line text, automatic ellipsis, and a 600 ms
name-only hover reveal when text was actually shortened (including an alias).
Full names remain searchable and accessible.

Choose `single` with one line, `path` with two, or `wrap` with one to six.
Middle ellipsis with `wrap` is invalid. Optional shrinking has a minimum font
size; boxes never grow automatically. For explicit pin/copy and keyboard-focus
reveal controls, choose `reveal_mode="controls"`. Enabling those controls in
delayed-hover mode raises `ValueError` at model construction. See the
[complete policy options](../README.md#fixed-box-node-labels).

## Extend, deploy, and diagnose

Prefer built-in styles and scalar metadata before writing a renderer. Static
PNG sprites use `SpriteCatalog` and do not require renderer enablement. A
renderer package is inert until explicitly enabled; PRIMS emits bounded SVG
primitives, JavaScript registers trusted same-origin code, and RASTER turns
primitives into packed image pages. JavaScript renderers are trusted code, not
a sandbox for user-provided scripts. Follow the
[renderer guide](contributing-renderers.md) and [CSP guide](transports-and-csp.md).

Equal atlas policies share a process cache. Limits apply per distinct policy,
not per user/session, with no aggregate ceiling across policies. `warm_atlas`
can prepare known domains, but does not eliminate every later image decode or
resize. Image-preparation caching and worker-based layout remain deferred.
Measure the actual graph/image workload before raising budgets: collapsed
collections reduce display work, not the cost of loading and serializing input.

| Symptom | First checks |
| --- | --- |
| `SGC_*` validation error | Read its node/edge subject; inspect IDs, types, ports, required badge data and input budget |
| Collection did not appear | Parent type declaration, exact edge type, distinct count, cutoff and display mode |
| Count exceeds visible members | Collapsed versus partially expanded versus omitted; loaded count is not display cost |
| Search misses a node or metric | Rendered membership, active scope, scalar field declaration, unknown versus zero |
| Positions change unexpectedly | Stable IDs/key, navigation anchor, geometry/group/order changes; appearance alone should not relayout |
| Labels disappear on scroll | Reveals intentionally close when the page/canvas moves |
| Reruns feel expensive | Which callback/event fired, uncached queries, data volume and image preparation |
| Images or JavaScript fail to load | Installed extras, enabled registry, valid assets, browser console and host CSP |

Support status and deliberate limits live in the [beta contract](beta-contract.md).
For a bug report, include installed core/contrib/Streamlit versions, browser,
minimal graph/schema, budget/group settings, reproduction steps and the diagnostic
code. Use synthetic data rather than credentials or private graph contents.
