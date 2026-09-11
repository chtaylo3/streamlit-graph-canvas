# Beta contract and implementation status

This document is the authoritative status overlay for
`generalized-node-canvas-design.md`. The design records the long-term
architecture; this table distinguishes the public beta contract from later
milestones.

| Area | Status for beta | Contract |
| --- | --- | --- |
| Core graph/schema model | Built | Directed multigraphs, explicit node/edge IDs, typed node/edge declarations, and application-owned graph meaning |
| NetworkX adapter | Built | Optional directed-graph conversion with unused source attributes preserved |
| Validation and budgets | Built | Strict JSON, geometry, endpoint, port, palette, primitive, and combined-element validation; failures use `SGC_*` diagnostics |
| Topology, layout, and presentation identities | Built | Graph presentation updates preserve topology identity; a separate layout hash also prevents schema appearance updates from rerunning ELK while preserving action validation |
| ELK layout | Built | Framework-owned geometry/group/order layout; appearance-only changes reuse layout; application positions remain deferred |
| Child grouping and budgets | Built | Per-parent-type, per-edge-category tree/collection/cutoff modes; loaded graph and rendered elements have separate limits |
| Search and labels | Built | Scalar metadata search and explicit Apply ordering are local; opt-in submission reruns Streamlit; fixed-box policies have global defaults and complete type overrides |
| Selection and viewport | Built for beta | Persistent across component remounts; removed nodes are reconciled; viewport commits at interaction end |
| Fit view | Built for beta | `never`, `initial`, and `topology-change` have distinct behavior; a restored viewport takes precedence over initial fitting |
| Action protocol | Built, intentionally narrow | Protocol v1 contains ordered, acknowledged, topology-validated node `click` actions only |
| Other gestures and handlers | Deferred | Double-click, context menu, domain expand/collapse callbacks, badge activation, handler routing, and click buffering require a future protocol version; built-in collection toggles are browser interactions |
| Node and edge styling | Built for beta | Symbolic palette tones control node fill/stroke/text/radius and edge stroke/width/dash |
| Named ports | Built for beta | Declared ports are rendered and edge source/target handles are honored |
| Accessibility | Built for beta with release checks | Named keyboard-operable nodes, visible focus, accessible badge text summaries, controls, and automated Chromium checks |
| Renderer discovery | Built | Import-free discovery, requested-only validation, explicit enablement, distribution-owned implementation imports, and diagnostics for malformed installed packages |
| PRIMS transport | Built | Closed rectangle/circle/text vocabulary with bounded output and theme-aware palette resolution |
| JavaScript renderer transport | Built | Explicitly enabled, hash-bound Components v2 bootstraps register trusted scoped-SVG factories; conflicts and missing registrations fail closed |
| Raster transport | Built | `Transport.RASTER` runs validated Python PRIMS through Pillow and the shared packed-page delivery path; legacy `Transport.ATLAS` compatibility remains for the 0.1 release-candidate series |
| Static PNG sprites | Built | Explicit catalogs map stable IDs to required light/default and optional dark PNGs; dark falls back to light, alpha is preserved, and paths/source bytes never enter the browser envelope |
| Atlas delivery | Built | Deterministic immutable pages contain one or more static or procedural raster tiles; node layers carry real crop coordinates, and page deltas use a bounded shared cache per distinct atlas policy and Blob URL lifecycle management |
| Other images, bleed sizing, and region helpers | Deferred | Remote sources, SVG, JPEG, WebP, animation, user-provided prepacked pages, bleed-driven layout, and the full region helper vocabulary are outside this beta contract |
| Observability | Built | OpenTelemetry metrics through the `otel` extra cover atlas cache behaviour and serialization timing, with opt-in browser metrics posted to an application-configured collector; internal `streamlit_graph_canvas` logging uses selected `sgc_` fields, and `canvas.explain()` remains outside the beta API |
| Performance caching | Partial | Verified manifest metadata may be cached; renderer-output caching waits for reproducible benchmarks and a purity/memory contract |
| CSP | Built and browser-tested | JavaScript requires same-origin scripts; raster and static sprite delivery add Blob images only; the complete Streamlit host policy is tested in Chromium |

## Protocol v1

Protocol v1 is deliberately limited to node clicks. Each action contains a
canonical UUID operation ID, a positive JavaScript-safe sequence, the current
topology revision, authoritative node ID/type, node target, and boolean
keyboard modifiers. Python validates the complete shape, ignores already
acknowledged actions, and discards otherwise valid actions for stale or unknown
topology. Malformed envelopes fail closed with a diagnostic.

The component envelope uses codec version 3. It adds static sprite bindings,
packed page descriptors, and physical crop rectangles. Older frontends must
reject codec 3 instead of treating a multi-sprite page as a one-tile image.

Selection and viewport are persistent state rather than action events. The
frontend retains the freshest state for component remounts, while Python
mirrors validated state in the Streamlit session and returns the acknowledged
action sequence in the next data envelope.

## Palette contract

Palette values are application-supplied CSS colors, not graph data. Beta
accepts hex colors, named colors, supported numeric CSS color functions, and
Streamlit custom properties in the form `var(--st-*)`. External/document paint
references, image functions, attributes, unbounded values, and arbitrary CSS
declarations are rejected. A tone may provide light and dark variants; the
frontend resolves those with the browser `light-dark()` color function.

## Static sprite and theme contract

`SpriteCatalog` entries contain a `StaticSprite` with a required `light`
`PngImage` and optional `dark` image. Light is the deterministic default. Dark
mode selects dark when supplied and silently falls back to light otherwise.
`SpriteBinding` supports `contain`, `cover`, and `fill`; its region is fixed
schema geometry and is independent of physical atlas coordinates and device
resolution.

Nodes refer to catalog IDs through `SpriteRef`. Catalog source paths and bytes
remain server-side, and static sprites are independent of renderer discovery
and enablement. Static and PRIMS-derived rasters share deterministic immutable
multi-sprite pages, the process-global content-addressed cache, page deltas, and
browser crop validation. A selected theme, resolution, sprite mapping, or page delta changes
presentation identity only and does not change topology or cause ELK layout.

The initial image scope is static PNG only. Remote fetches, runtime URLs, SVG,
JPEG, WebP, GIF/animation, and caller-provided packed pages or coordinates fail
closed or are not accepted by the public API.

## Compatibility policy

- Python 3.12, 3.13, and 3.14 are tested on Windows and Linux; newer Python
  versions remain forward/advisory until promoted.
- Streamlit 1.62 is the minimum; CI tests the minimum and the current locked
  version. A scheduled lane tests the newest prerelease without blocking normal
  development.
- The clean-wheel browser gate uses pinned Chromium on Ubuntu and tests
  core-only, stock contrib, and hostile-fixture environments.
- Node.js 24.x is the supported frontend build toolchain.
- Firefox, WebKit, and ARM64 remain best-effort. JavaScript, raster, atlas crop,
  and static sprite paths are in the clean-wheel Chromium release matrix.

An upper Streamlit dependency bound is added only for a demonstrated
incompatibility. Known-bad versions must instead produce an actionable runtime
diagnostic and be excluded by the release compatibility policy.

### OpenTelemetry metrics

Metrics are available through the `otel` extra:

```
pip install "streamlit-graph-canvas[otel]"
```

The contract:

- The package depends on `opentelemetry-api` only, never the SDK, so it never
  competes with the application's own telemetry configuration.
- Telemetry flows to whichever provider the application installs. The package
  never configures a provider, an exporter, or a reader.
- Instruments are inert when no provider is configured and when the extra is not
  installed. Neither case raises.
- Metric names and attributes fall under this module's semantic versioning, and
  a breaking change in OpenTelemetry is a breaking change of this module.
- Metrics are intended for engineers and developers operating the component
  rather than as an application-facing API.

Server-side instruments, all with bounded or absent attributes:

| Instrument | Type | Attributes |
| --- | --- | --- |
| `sgc.atlas.tile.lookups` | Counter | `result` is `hit` or `miss` |
| `sgc.atlas.pages.evicted` | Counter | none |
| `sgc.atlas.failures` | Counter | `code` is a diagnostic code |
| `sgc.atlas.pages.resident` | UpDownCounter | none |
| `sgc.atlas.bytes.resident` | UpDownCounter | none |
| `sgc.atlas.pack.duration` | Histogram, seconds | none |
| `sgc.serialize.duration` | Histogram, seconds | none |

Browser-side metrics are opt-in through `telemetry_endpoint`:

```python
result = graph_canvas(
    graph,
    schema,
    key="dependencies",
    telemetry_endpoint="https://otel.internal:4318/v1/metrics",
)
```

The browser posts OTLP/HTTP JSON directly to that collector rather than
tunnelling metrics through Streamlit's widget channel, because `setStateValue`
and `setTriggerValue` each force a full script rerun and a per-flush rerun would
defeat the purpose. Points are buffered and flushed on a timer and on unmount,
using `sendBeacon` where available. A failed flush drops one interval and never
disturbs a render.

That direct post requires the collector origin in `connect-src`. Pass the same
URL to `streamlit_host_csp(telemetry_endpoint=...)` to obtain the policy. Browser
instruments are `sgc.browser.mounts`, `sgc.browser.graph.size`,
`sgc.browser.atlas.apply.duration`, and `sgc.browser.failures`, whose `code`
attribute carries only the bounded diagnostic prefix and never a message body.

### Atlas warming

`warm_atlas` pre-packs raster tiles for a declared value domain:

```python
from streamlit_graph_canvas import warm_atlas

warm_atlas(
    schema,
    {"service": {"severity": ["critical", "high", "medium", "low"]}},
    renderer_registry=registry,
)
```

Sessions using the same atlas policy can reuse those packed pages. Warming does
not eliminate per-call validation or image preparation. Only bindings whose
transport rasterizes are packed; PRIMS bindings render per request and never
enter the atlas.

### Breaking change during 0.1: atlas cache scope

`AtlasScope`, the `atlas_tenant` parameter, and the `AtlasPolicy` fields `scope`,
`max_tenant_pages`, and `max_tenant_bytes` are removed. The atlas cache is
content-addressed and process-global, so sessions using an equal policy share
tiles. Distinct policies have separate caches. Passing `atlas_tenant` raises
`SGC_ATLAS_TENANT_REMOVED` rather than being ignored, because silently dropping a
security-shaped parameter would be worse than breaking.

`max_pages` and `max_bytes` change meaning. They were a per-session allowance and
are now a ceiling per distinct policy cache shared across sessions. Sessions
using the same policy share that allowance. There is no aggregate process-wide
ceiling across different policies: their residency adds up. Reuse stable policies
and use `atlas_cache_snapshot()` to inspect aggregate residency.

Page identifiers change from a process-keyed HMAC to `sha256` over the packed
page bytes and tile mapping. They are now stable across processes, so a browser
keeps a cached page across a server restart.

## Security and CSP behavior

All executable assets are wheel-packaged and same-origin. JavaScript renderer
factories are trusted page-level code; raster and static sprite delivery create
only PNG Blob URLs. Neither path performs a runtime third-party fetch. Static
PNG source paths and bytes remain on the server. Shadow DOM is style isolation,
not a security sandbox. Enabled Python and JavaScript renderers must be reviewed
like any other dependency.

See `transports-and-csp.md` for the tested policy, the distinction between host
and transport allowances, atlas cache scope, and deployment guidance.

### Child display and edge presentation

`ChildGroup` declarations on a `NodeType` are evaluated independently per edge
relationship. `GroupDisplay.TREE` leaves children directly in the graph;
`COLLECTION` groups every nonempty category; `CUTOFF` groups at or above
`threshold` (the default remains cutoff). Counts are distinct child IDs, so
parallel edges do not inflate them. `collapsed` controls initial disclosure
independently of the display mode. Empty categories create no container.
Expansion stays browser-local with eager delivery. A toggle survives display
policy changes during the mounted component's lifetime; remounting resets it.
Selection remains authoritative even if a selected member becomes hidden.

`Edge.emphasized` and `Edge.optional` are presentation modifiers. Neither changes
relationship identity or the topology hash. Emphasis uses the `accent` palette
color and a stronger stroke; optional edges use a dotted stroke. Both compose
with dimming and the schema's relationship style.

Expanded members use ELK layered orthogonal routing inside their container.
The frontend renders its bend points in canvas coordinates instead of replacing
them with generic curves. Edge merging is disabled and lanes are spaced to
avoid coincident segments. ELK optimizes placement and routing heuristically:
this is not a guarantee of globally shortest paths or crossing-free drawings
for arbitrary dense/nonplanar graphs. Cycles and disconnected members are
supported. Shared members of multiple expanded groups stay outside containers
with their original relationships visible. Cross-container connections and
explicit-port edges use the renderer's smooth-step fallback; internal routing
constraints do not guarantee obstacle avoidance for those boundary connections.
Node outlines use zoom-compensated SVG strokes to remain readable at low zoom.

### Edge arrow placement

`EdgeStyle.arrow` accepts `"none"` (the backward-compatible default), `"source"`,
`"target"`, or `"both"`. Arrowheads follow the directed edge endpoints and use the
edge's palette color, including its emphasized color. They work with routed and
explicit-port edges. Collection connectors inherit their relationship type's
arrow placement. Applications decide which relationship types should be directed
visually; dependency-specific badges and path selection remain application logic.

### Loaded data and rendered-element budgets

`graph_canvas(..., max_elements=700, max_loaded_elements=20_000)` separates the
rendered scene from the loaded graph. The default input limit is the greater of
20,000 and `max_elements`; JSON and renderer validation still apply. Direct calls
to `serialize_graph` and `validate_graph` retain their input-budget semantics.

The display budget counts real visible nodes and edges plus synthetic collections:

- A collapsed collection costs two elements: its node and its parent edge.
- Expansion adds one element per displayed member and each actually drawn internal
  or cross-collection edge. Replaced parent-to-member edges never count.
- Ancestor context, shared members, parallel edges, and self-loops count according
  to what is actually rendered. Shared nodes are counted once.

All loaded members remain in the collection total. If expansion cannot fit,
the marker and header report the shown count alongside the total, and a notice
reports display omissions. Collapsing other collections or raising `max_elements`
can reveal more members without reloading the graph. Focus and ancestor context
have priority; optional same-type siblings use remaining space. Tree mode counts
individual parent-to-child edges normally. Very small budgets may omit entire
collections, which the notice reports separately.

Transitions discard outgoing items early if retaining them would exceed the
display budget. The app can impose its own separate input cap, but should not
truncate a collection against the display budget before passing it to the component.

### Optional sibling context

Applications can opt into sibling context before calling `graph_canvas`:

```python
from streamlit_graph_canvas import add_sibling_context

view = add_sibling_context(
    visible=view,
    available=full_graph,
    anchor_id=current_repository_id,
    enabled=True,
    opacity=0.2,  # 20% opaque; 80% transparent
    max_elements=500,
    relationship_types=frozenset({"owns"}),
)
```

The anchor and its parent must already be visible. The helper adds same-type
siblings under those parents, plus their connecting edges, in label/ID order.
It never loads siblings' descendants or removes anything from the existing view.
This helper limits loaded nodes plus edges, including parallel edges; pass an
input budget here, independently of the canvas display budget. Candidates
that do not fit are skipped. An already oversized view raises `ValueError`.
`enabled=False` returns the original view. Available and visible graphs should
use consistent, unique node and edge IDs. The helper has no NetworkX dependency.

`Node.opacity` and `Edge.opacity` accept finite values from 0 to 1; `None` preserves
existing dimming behavior. Explicit opacity overrides dimming and changes only
presentation, not topology. Context nodes remain interactive. Developers may
hard-code the arguments or supply values from their own UI controls; the package
adds no end-user controls automatically.

Sibling context assigns `Node.layout_order` hints to both focused and context
peers using stable label/ID order. When hints are present, the layered layout
preserves model order for the explicitly ranked peers. Unranked descendants
and containers remain free to optimize their layout; connector ordering is not
derived from sibling ranks. This lets long direct edges use interior gaps rather
than being forced around unrelated dependency nodes. Nodes may
still shift to make room for different descendants; this is an ordering guarantee,
not fixed pixel coordinates. Applications can also set integer `layout_order`
hints explicitly. `None` retains the default layout behavior.

`FitView.INITIAL` preserves an existing viewport when topology changes; it fits
only when the canvas has no saved viewport. `TOPOLOGY_CHANGE` retains automatic
fitting after topology changes.

### Navigation transitions

`graph_canvas(..., transition_ms=250, navigation_anchor=focused_node_id)` keeps a
persistent canvas while topology changes. Shared nodes move between layouts;
entering and outgoing nodes and their edges fade together. The optional anchor
aligns the shared node's world position before movement; when fitting is enabled,
the viewport pans and zooms smoothly to frame the destination. INITIAL/NEVER
preserve the current viewport during subsequent navigation. When successive
anchors share a parent, existing ancestors and siblings retain their world
positions and unchanged connecting paths. This also applies to collection toggles
at the same anchor; the active branch can still change its layout.

Duration accepts integer milliseconds from 0 to 1000; 0 disables motion. The
browser's `prefers-reduced-motion: reduce` preference always disables animation,
including viewport interpolation. Apps can hard-code these options or expose them
as controls. The example explorer supplies its focused node and uses 250 ms.

The previous scene stays visible while ELK computes the next layout. New layouts
ignore stale layout results and restart animation from the currently displayed
positions. Exiting nodes are inert and removed at completion. Collection members
use world coordinates during animation and return to container-relative
coordinates afterward. Routes are interpolated with their nodes; intermediate
routes need not remain orthogonal. Unchanged paths retain their exact bends throughout animation. Final routes use
ELK paths where valid; connections whose endpoints were repositioned to preserve
context use the normal handle-aware edge renderer.

Transitions temporarily retain the old and new visible scenes, not additional
hierarchy data. Interrupted transitions discard older outgoing ghosts instead of
accumulating them. Sprite page leases remain valid until the outgoing scene is
retired. Animation frames stay local to the browser; only the settled viewport is
reported to Streamlit. Pointer and wheel input stop automatic viewport movement.
