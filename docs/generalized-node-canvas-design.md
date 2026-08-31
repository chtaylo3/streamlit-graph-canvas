# Generalized node canvas for Streamlit

This design defines a reusable, domain-neutral graph canvas for Streamlit. It
is for reviewers evaluating the architecture and for engineers implementing
the core package, renderer ecosystem, atlas transport, and conformance tests.
The proposal targets Streamlit Components v2 and replaces the
dependency-specific contract in the GitHub Dependency Explorer.

Status: Proposed

## Contents

- [Background](#background)
- [Major revisions to the reviewed proposal](#major-revisions-to-the-reviewed-proposal)
- [Goals](#goals)
- [Non-goals](#non-goals)
- [Critical design invariants](#critical-design-invariants)
- [Support matrix](#support-matrix)
- [Repository and package structure](#repository-and-package-structure)
- [Core data model](#core-data-model)
- [Renderer packages](#renderer-packages)
- [Badge bindings, regions, and paint order](#badge-bindings-regions-and-paint-order)
- [Transport model](#transport-model)
- [Image references](#image-references)
- [Serialization and revisions](#serialization-and-revisions)
- [Layout, sizing, and viewport behavior](#layout-sizing-and-viewport-behavior)
- [Element budget](#element-budget)
- [State and action protocol](#state-and-action-protocol)
- [Hit testing and accessibility](#hit-testing-and-accessibility)
- [Validation and failure behavior](#validation-and-failure-behavior)
- [Observability](#observability)
- [Security and privacy considerations](#security-and-privacy-considerations)
- [Performance validation](#performance-validation)
- [Implementation plan](#implementation-plan)
- [Test strategy](#test-strategy)
- [Compatibility and release policy](#compatibility-and-release-policy)
- [Licensing and release artifacts](#licensing-and-release-artifacts)
- [Alternatives considered](#alternatives-considered)
- [Trade-offs and risks](#trade-offs-and-risks)
- [Rollout and rollback](#rollout-and-rollback)
- [Open questions and release prerequisites](#open-questions-and-release-prerequisites)

## Background

The [GitHub Dependency Explorer](https://github.com/chtaylo3/streamlit-canvas-graph)
contains a React Flow canvas with ELK layered layout and position preservation
across Streamlit reruns. Those behaviors are useful outside the application,
but the component contract hardcodes account, repository, manifest, dependency,
and vulnerability concepts.

The existing component also sends a base64-encoded PNG thumbnail for every
node on each rerun. The planning baseline estimates about 2.3 MB of transfer
and 50 MB of decoded bitmap data for a 500-node graph. These values are
assumptions, not verified benchmarks. The beta validation phase measures the
same workload before the project treats them as evidence.

The existing repository uses Components v1. Components v2 changes the security
and communication model: component JavaScript runs in the application page,
not in an iframe, and state and triggers have distinct persistence semantics.
The [Streamlit Components v2 API reference](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component)
defines this execution model. This design therefore treats the existing
implementation as a behavioral reference rather than as a frontend
architecture to preserve.

## Major revisions to the reviewed proposal

This design makes the following changes to the original proposal:

- Targets Components v2 only and removes all iframe assumptions.
- Keeps core and contrib in one monorepo while publishing them as separate
  Python distributions.
- Defers `graph-window` until a second independent consumer establishes its
  API requirements.
- Uses a package-native `GraphData` model and provides NetworkX through an
  optional adapter.
- Supports directed multigraphs, explicit edge IDs, self-loops, parallel
  edges, and named ports.
- Removes containment semantics from the canvas schema. Applications own
  relationship meaning and graph windowing.
- Includes PRIMS, JavaScript, and ATLAS in the first public beta.
- Loads third-party renderers only from explicitly enabled, installed Python
  wheels with static manifests.
- Uses Components v2 bootstrap components to register JavaScript renderers in
  a namespaced page-local registry.
- Replaces public atlas URLs and append-only caches with binary page deltas,
  session-scoped bounded caches, and browser Blob URLs.
- Separates persistent selection and viewport state from ordered action
  triggers.
- Makes Python authoritative for topology during expand and collapse actions.
- Changes the graph limit to a configurable combined node-and-edge budget with
  a default of 700 elements.
- Defines accessibility, observability, compatibility, and release gates as
  first-release requirements.
- Treats the tenfold payload reduction as a measured beta target, not a
  stable-release blocker.

## Goals

- Publish a domain-neutral Streamlit component for arbitrary directed graphs.
- Let an application declare node types, edge types, ports, styles, badge
  bindings, and interactions as data.
- Support Python and JavaScript badge renderers through one versioned extension
  contract.
- Support PRIMS, JavaScript, and ATLAS delivery without requiring an
  application to redesign badge data when it changes transports.
- Preserve node positions and the viewport across Streamlit reruns.
- Distinguish single-click and double-click actions without emitting a stray
  single-click action for a double-click.
- Provide keyboard, pointer, touch, and screen-reader access to every supported
  interaction.
- Reproduce the Dependency Explorer canvas through public APIs and separately
  distributed renderer packages.
- Measure payload, memory, layout, rendering, and atlas behavior against a
  representative beta workload.

## Non-goals

- Supporting Components v1.
- Replacing React Flow or ELK.
- Providing layout engines other than ELK in the first release.
- Accepting application-provided node positions in the first release.
- Editing graph topology directly in the browser.
- Providing framework-defined containment, breadcrumb, or graph-windowing
  semantics.
- Providing custom node-body or edge renderers in the first release.
- Loading renderer code from graph data, arbitrary paths, remote URLs, or npm
  at application runtime.
- Sandboxing enabled JavaScript renderer packages.
- Providing graph analytics, authentication, authorization, data access,
  static export, printing, or a visual schema editor.
- Supporting ARM64 or end-user platforms other than Windows 11 in the first
  release.
- Guaranteeing operation on graphs beyond the configured element budget.
- Providing cross-session exactly-once action delivery.

## Critical design invariants

The implementation and review process must preserve these decisions. A change
to any invariant requires an explicit design update and compatibility review.

- Graph data never selects or loads Python or JavaScript code.
- Python owns graph topology; the browser may show pending presentation but
  never invents authoritative nodes or edges.
- Selection and viewport use persistent Components v2 state. Ordered actions
  use triggers, sequence numbers, acknowledgments, and deduplication.
- Click and double-click remain distinct actions. When both are enabled, a
  double-click never emits a stray click action.
- Presentation-only changes never run ELK.
- Badge data never changes geometry. Type defaults and explicit per-node
  dimensions are the only node-size inputs.
- Manifest, compatibility, and registration failures are fatal outside the
  explicit lenient development-preview mode.
- Enabled JavaScript renderer wheels are trusted page-level code, not sandboxed
  plugins.
- Renderer API version 1 remains stable from the first public beta.

## Support matrix

The first public release uses the following minimums and test boundaries:

| Area | Supported target |
| --- | --- |
| Python | 3.12 or later within the tested release matrix |
| Streamlit | 1.62.0 or later within the tested release matrix |
| Frontend development | Node.js 24 or later |
| Streamlit runtime | Windows 11 and Linux x86-64 |
| End-user operating system | Windows 11 |
| Browsers | Latest two stable Microsoft Edge and Google Chrome releases |
| Firefox | Best effort until it joins the automated matrix |
| ARM64 | Deferred |

The package documentation must identify the exact tested versions for each
release without implying support for untested combinations.

## Repository and package structure

The repository is named `streamlit-graph-canvas`. It contains two publishable
Python distributions:

| Distribution | Import package | Responsibility |
| --- | --- | --- |
| `streamlit-graph-canvas` | `streamlit_graph_canvas` | Schema, component, layout, renderer contracts, transports, events, validation, and diagnostics |
| `streamlit-graph-canvas-contrib` | `streamlit_graph_canvas_contrib` | Stock renderers implemented only through the core public API |

The monorepo shares development tooling, tests, examples, and release checks.
Each distribution builds and installs independently. Contrib depends only on
the documented core API and must not import private modules.

The Dependency Explorer remains in its own repository. Before publication, a
clean integration test installs built core and contrib wheels and reconstructs
the explorer canvas through public APIs.

The proposed `graph-window` distribution is deferred. Windowing and breadcrumb
helpers remain in the Dependency Explorer until all of the following are true:

- A second independent application needs the helpers.
- Containment mapping and breadcrumb behavior have stable contracts.
- Node-budget and edge-budget semantics are defined for traversal.
- Traversal tests cover multigraphs, cycles, and named ports where relevant.

## Core data model

### Graph data remains independent of NetworkX

`GraphData` is the package-native typed model. The public model contains nodes,
edges, and their instance data without requiring NetworkX at runtime.

An optional `from_networkx()` adapter converts supported NetworkX graphs into
`GraphData`. The adapter preserves explicit IDs, multigraph edge keys, port
metadata, and type names. NetworkX remains in the Dependency Explorer and in
adapter-specific tests, not in the core dependency set.

### Nodes and edges have explicit identities

Every node has a stable string ID and a declared node type. Every edge has a
stable string ID, source node ID, target node ID, edge type, and optional named
source and target ports.

The first release supports directed multigraphs. It accepts parallel edges and
self-loops and never derives an edge identity only from its endpoints.

### Schema declarations remain separate from instance data

The schema contains stable declarations that usually remain unchanged across
reruns. Graph data contains instance values that may change frequently.

```python
@dataclass(frozen=True)
class GraphSchema:
    node_types: Mapping[str, NodeType]
    edge_types: Mapping[str, EdgeType]
    palette: Mapping[str, ToneSpec]


@dataclass(frozen=True)
class NodeType:
    name: str
    style: NodeStyle
    ports: tuple[PortSpec, ...] = ()
    badges: tuple[BadgeBinding, ...] = ()


@dataclass(frozen=True)
class EdgeType:
    name: str
    source_types: frozenset[str] | AnyNodeType
    target_types: frozenset[str] | AnyNodeType
    style: EdgeStyle = EdgeStyle()
```

`EdgeType` validates allowed endpoint types. It does not contain a built-in
`contains` or `references` semantic. Relationship meaning belongs to the host
application.

### Node geometry is declared and bounded

A node type supplies default width and height. A node instance may override
either dimension explicitly. Badge regions use binding options and node
geometry only; badge data never changes region size.

Renderers must fit, clip, or abbreviate variable data within the declared
region. Automatic content measurement is deferred because it would make data
changes trigger layout and would produce platform-dependent results.

### Node bodies and edges remain framework-owned

The first release provides declarative node-body and edge styling. Renderer
packages draw badge regions only. They cannot replace node bodies, edge paths,
ports, hit testing, or accessibility structure.

Custom node bodies and custom edge renderers remain deferred. Revisit custom
edge rendering after real use cases establish requirements for ports,
multigraph routing, keyboard behavior, labels, accessibility, and hit testing.

## Renderer packages

### Distribution and discovery

Every renderer package ships as a Python wheel, including a package whose
renderer is implemented only in JavaScript. JavaScript dependencies are built
into a self-contained ES module before the wheel is published. Applications do
not need Node.js to run the component.

The wheel follows Streamlit's
[package-based Components v2 model](https://docs.streamlit.io/develop/concepts/custom-components/components-v2/package-based).
All files in a declared component asset directory are public. A renderer wheel
must not place credentials, private graph data, source maps containing secrets,
or internal-only files in that directory.

Installed renderer distributions advertise themselves through the
`streamlit_graph_canvas.renderers` Python entry-point group. A static TOML
manifest inside the distribution contains the metadata needed for diagnostics.
Discovery may read distribution metadata and the manifest, but it must not
import Python modules or execute JavaScript.

An application explicitly enables a renderer package before any of its code
loads. The graph schema and graph payload cannot enable a package.

### Manifest requirements

Each manifest declares at least the following values:

- Distribution name and version.
- Manifest schema version.
- Compatible renderer API range.
- Globally namespaced renderer kinds.
- Available Python and JavaScript implementations.
- Supported transports for each kind.
- Packaged JavaScript assets and content hashes.
- Packaged fonts and other public assets.
- Required framework capabilities.

Canonical kinds use a globally namespaced form such as `vendor/package/rings`.
An application may declare local aliases, but serialized data and diagnostics
retain the canonical ID.

Absolute paths, path traversal, missing files, hash mismatches, duplicate
canonical kinds, and incompatible API ranges are startup errors.

### Renderer API compatibility

The renderer API has a version independent of the Python distribution version.
Manifests declare a compatible range such as `>=1,<2`.

Renderer API version 1 becomes stable with the first public beta. Additive
changes retain version 1. Breaking changes require version 2. An enabled
renderer with an incompatible range fails startup validation before graph data
is serialized.

### Python renderer contract

A Python renderer measures static options and emits a closed vocabulary of
drawing primitives.

```python
class BadgeRenderer(Protocol):
    kind: str
    renderer_api: int

    def measure(self, options: Options, node: NodeGeometry) -> Size: ...
    def render(
        self,
        data: object,
        options: Options,
        context: BadgeContext,
    ) -> Sequence[Prim]: ...
    def raster_key(self, data: object, options: Options) -> str | None: ...
```

The primitive vocabulary contains rectangle, circle, path, arc, text, image,
group, linear gradient, and clip primitives. It does not contain raw markup,
scripts, event attributes, `foreignObject`, or arbitrary external references.

### JavaScript renderer registration

Components v2 does not provide an iframe security boundary. Enabled JavaScript
renderers execute with the same application-page privileges as the core
component.

Each enabled JavaScript renderer wheel registers a JavaScript-only Components
v2 bootstrap component. Python mounts the bootstrap before the canvas. The
bootstrap adds renderer factories to a versioned page-local registry stored
under a framework-owned global symbol.

Registration is idempotent for the same canonical kind, package version, asset
hash, and API version. A conflicting registration is fatal. The core does not
evaluate source strings, create executable Blob URLs, or fetch renderer code
from an external origin.

The canvas receives the required canonical kinds and expected asset hashes in
its configuration. It waits for the corresponding bootstrap registrations
before rendering graph content. A missing, late, or conflicting registration
produces a fatal mount diagnostic and prevents the canvas from rendering with a
partial registry.

The application must reload the page after changing the enabled renderer set.
Development documentation must state this lifecycle requirement.

### Shadow-DOM boundary

The core component uses Components v2 style isolation. React Flow, controls,
menus, overlays, and renderer output remain inside the component shadow root.
Renderers receive scoped target elements and must not append UI to
`document.body`.

This boundary prevents accidental CSS and lifecycle conflicts. It does not
sandbox JavaScript, and an enabled renderer can deliberately escape it.

## Badge bindings, regions, and paint order

A badge binding belongs to a node type. It selects a renderer kind, region,
transport, layer, and static options. A node instance supplies only the varying
data for bindings declared by its type.

```python
@dataclass(frozen=True)
class BadgeBinding:
    name: str
    kind: str
    region: Region
    transport: Transport = Transport.PRIMS
    layer: Literal["under", "over"] = "over"
    z: int = 0
    required: bool = False
    options: Mapping[str, object] = field(default_factory=dict)
```

The first release provides the following region constructors:

| Constructor | Result |
| --- | --- |
| `Region.anchor()` | Fixed box at a compass anchor, with optional stacking |
| `Region.edge()` | Strip along a node edge |
| `Region.surround()` | Box expanded around the node |
| `Region.fill()` | Node-sized overlay with an optional inset |
| `Region.at()` | Explicit node-local rectangle |

The framework computes a bleed box that contains the node and all its regions.
ELK lays out the bleed box so edges account for badges outside the node body.
A property test verifies that every resolved region remains inside it.

SVG uses document order for painting. The serializer sorts bindings by layer,
`z`, and declaration index. A renderer must not reparent its output outside the
assigned layer.

## Transport model

Transport is selected per badge binding. All transports share the same kind,
options, region, data contract, paint order, and event envelope.

| Transport | Browser input | Zoom behavior | Part-level interaction |
| --- | --- | --- | --- |
| PRIMS | Validated drawing primitives | Vector-sharp | Supported |
| JavaScript | Raw validated badge data | Vector-sharp | Supported when the renderer declares parts |
| ATLAS | Content hash and tile coordinates | Raster; bounded by generated resolution | Not supported |

Switching between supported transports changes only the binding configuration.
It does not require a new kind or application payload.

### PRIMS

Python renderers emit validated primitives. The browser interprets symbolic
tone names against Streamlit theme variables, which lets PRIMS respond to theme
changes without a Python rerun.

PRIMS moves cost from transfer bytes to SVG elements. The frontend enables
React Flow viewport culling, and beta measurements determine which renderers
benefit from ATLAS instead.

### JavaScript

JavaScript renderers receive validated raw data and a scoped SVG context. The
renderer marks interactive subparts through the framework API rather than by
installing independent event handlers.

JavaScript packages are trusted application dependencies. Explicit enablement
is a consent boundary, not a sandbox.

### ATLAS

ATLAS rasterizes the output of a prim-emitting Python renderer. A renderer that
cannot emit primitives cannot use ATLAS.

The provisional rasterizer is `resvg_py`, isolated behind an internal
`SvgRasterizer` interface and installed through the `atlas` extra. The beta
matrix validates its license, wheel availability, output, and failure behavior
on Windows and Linux x86-64. Its API does not appear in the public contract.

The atlas pipeline performs the following work:

1. Compute a content key from the canonical kind, renderer version, static
   options, badge data, resolved palette, theme, dimensions, font resources,
   and resolution bucket.
2. Reuse existing content-addressed tiles from the session cache.
3. Render missing keys to primitives and serialize them to the supported static
   SVG subset.
4. Rasterize and pack missing tiles into lossless PNG pages with alpha support.
5. Send new or changed pages as binary Components v2 data and send mappings as
   versioned JSON-compatible metadata.
6. Create browser-session Blob URLs and revoke each URL when its page leaves
   the browser cache.

Python and browser caches use configurable least-recently-used limits for page
count and total bytes. Cache eviction produces explicit removal deltas. The
cache is not append-only.

Session-scoped caching is the default because graphs may contain private data.
Global cache sharing requires explicit application opt-in and accepts only
non-sensitive, content-addressed tiles.

ATLAS supports `1x`, `1.5x`, and `2x` device-pixel-ratio buckets. The browser
rounds up to the nearest bucket and reports bucket changes through persistent
component state. Values above `2x` use `2x` until a later release adds another
bucket.

ATLAS generates light and dark variants lazily. A theme change reports the new
mode through component state and causes one rerun. The frontend retains the
previous tile or a neutral placeholder until the requested variant arrives.

ATLAS renderers use only fonts declared and packaged in their wheel. Core and
contrib package a deterministic open-licensed sans-serif font for stock
renderers. Unsupported glyphs produce an isolated badge diagnostic instead of
silently substituting an operating-system font.

## Image references

Renderers use structured image references:

- `PackageAsset(package, path)` identifies a public asset inside an installed
  renderer distribution.
- `BinaryImage(media_type, content_hash, bytes)` carries validated image bytes.
- `RemoteImage(provider, resource_id)` identifies a resource through an
  application-configured provider.

Python resolves `PackageAsset` only inside the asset roots declared by the
enabled renderer manifest. It validates the path, reads and hashes the file,
and sends the content through a session-scoped binary asset delta. The browser
creates a Blob URL and reuses it by content hash. The graph envelope never
contains an operating-system path or a cross-package asset URL.

Remote images are disabled by default. If an application enables them, it must
configure exact HTTPS origins and a provider. The framework rejects wildcard
hosts, embedded credentials, arbitrary ports, IP literals, private or local
addresses, and cross-origin redirects. Python and JavaScript enforce the same
policy.

The provider materializes every remote image as validated bytes before it
reaches a transport. The rasterizer and framework-managed browser renderers
never fetch the remote URL. Limits apply to encoded bytes, decoded bytes,
dimensions, and total payload.

An enabled JavaScript renderer can bypass the framework image API because it is
trusted page-level code. Renderer-authoring documentation must state this
boundary.

## Serialization and revisions

The first release uses versioned JSON-compatible envelopes for schemas,
topology, presentation data, primitives, mappings, state, actions, and
diagnostics. Raw bytes appear only in content-addressed image and atlas page
deltas.

Topology and presentation have separate hashes and monotonic revisions.
Topology contains IDs, endpoint relationships, ports, types, and geometry.
Presentation contains labels, styles, flags, selection, dimming, focus, and
badge data.

This separation fixes the existing behavior in which focus-only or dimming-only
changes can trigger ELK. A presentation-only revision never starts layout.

The internal envelope includes a codec version. A later release may negotiate
Arrow or another binary codec without changing `GraphData` or the public
renderer model.

## Layout, sizing, and viewport behavior

ELK is the only public layout engine in the first release. An internal
`LayoutEngine` interface keeps ELK configuration out of `GraphData`, renderer
contracts, and event envelopes. This boundary preserves a future path for
application-provided node positions without promising that feature now.

The component performs a full ELK layout when any of the following values
change:

- Topology.
- Node or port geometry.
- Schema geometry.
- ELK options.

Presentation, selection, viewport, theme, and badge data changes do not run
ELK. Incremental and constrained layout remain deferred.

The canvas defaults to `width="stretch"` and `height=620`. It accepts a
positive pixel height or `"stretch"` when the parent supplies a bounded height.
It rejects `"content"` because a graph viewport has no natural content height.

The frontend fills the Components v2 wrapper and uses `ResizeObserver` to
update React Flow, following Streamlit's
[component mounting and layout contract](https://docs.streamlit.io/develop/concepts/custom-components/components-v2/mount).
Wrapper resize never runs ELK.

`fitView` accepts `never`, `initial`, or `topology-change` and defaults to
`initial`. Resizing the wrapper does not change this policy.

## Element budget

The framework validates a combined element budget before serialization:

```text
len(nodes) + len(edges) <= max_elements
```

`max_elements` defaults to 700 and is configurable by the application. The
framework raises an actionable error when the graph exceeds the budget. It
does not truncate silently or choose a subgraph. The host application owns
windowing and truncation messaging.

The budget protects payload, layout, browser rendering, event processing, and
accessibility-tree size. Beta measurements validate the default rather than
treating it as a claim of universal capacity.

## State and action protocol

### Persistent state remains separate from actions

Components v2 state stores values whose latest value matters:

- Selected node IDs.
- Viewport position and zoom.
- Active theme and atlas resolution bucket.
- The last topology revision presented by Python.

Selection supports `none`, `single`, and `multiple` modes and defaults to
`single`. The first release selects nodes only; edge selection is deferred.

The frontend commits viewport state when a pan or zoom interaction ends, not on
every animation frame. This debounce preserves the final viewport without
causing a Streamlit rerun during each pointer movement.

Components v2 triggers carry ordered actions that must not coalesce, including
enabled click, double-click, context-menu, expand, collapse, and badge
activation actions.

### Handler routing determines emitted actions

The Python handler registry is the default source of truth for which actions
cross the frontend boundary. If no handler can consume a gesture for a node
type or badge part, the frontend does not emit it.

Applications that inspect returned actions directly may provide an explicit
per-node-type emission override. `None` derives behavior from handlers, while
an empty set suppresses actions. `canvas.explain()` shows the resolved routing
and whether click buffering is active.

Startup validation rejects handlers for undeclared node types, bindings, or
parts and rejects part-specific handlers for ATLAS bindings.

### Actions use a versioned envelope

Every action uses a common envelope:

```typescript
type CanvasAction = {
  protocolVersion: number
  seq: number
  operationId: string
  gesture: "click" | "dblclick" | "contextmenu" | "expand" | "collapse" | "badge"
  nodeId: string
  nodeType: string
  topologyRevision: number
  target:
    | { kind: "node" }
    | { kind: "badge"; binding: string; part: string | null }
  modifiers: { shift: boolean; meta: boolean; alt: boolean }
}
```

The envelope contains identifiers and interaction context, not labels or badge
payload values. The `operationId` remains stable across duplicate delivery.

### Action delivery is at least once within a session

Each component instance assigns a monotonically increasing sequence number to
actions. The frontend retains unacknowledged actions and sends the ordered
queue as a trigger value. Python processes sequence numbers above the last
acknowledged value in order, stores the highest handled sequence for the
component session, and returns an acknowledgment in the next data envelope.

Duplicate delivery is expected and safe. Python deduplication makes normal
handler execution effectively once within one Streamlit session. Browser
reloads, new sessions, and external side effects remain outside the guarantee.

Applications that perform non-idempotent external work must use the action
sequence or operation ID as their own idempotency key.

### Single-click and double-click remain distinguishable

If a node type has both click and double-click behavior, the frontend buffers
the click action for the double-click interval. A second click cancels the
pending click and emits one double-click action. If the node type has no
double-click behavior, the frontend emits the click immediately.

Selection may update immediately on the first click because selection is
persistent state rather than the buffered action. Tests verify that a
double-click produces one double-click action and no stray click action.

### Python remains authoritative for topology

Expand and collapse actions request a topology change. The browser may display
a temporary pending indicator, but it never adds, removes, or invents nodes or
edges.

Each request includes an action sequence and operation ID. Python responds with
the authoritative graph, topology revision, and resolved operation sequence.
The frontend ignores stale revisions, applies the authoritative topology, and
then merges retained positions for surviving nodes.

Duplicate actions are deduplicated. Rejected actions, errors, and timeouts clear
the pending presentation without changing topology. Tests cover delayed,
duplicate, stale, rejected, rerun, and reconnect cases.

A pending topology request does not block panning, zooming, selection, or
unrelated actions. The frontend prevents only a duplicate unresolved operation
for the same target when the application configures that restriction.

## Hit testing and accessibility

Badge layers are inert by default. A renderer must explicitly declare an
interactive part through the renderer API. One delegated listener on the node
wrapper resolves node and badge targets so ordering and click buffering remain
consistent.

The bleed-box wrapper is inert. The visible node body and declared badge parts
accept pointer input. Thin interactive paths may provide a wider invisible hit
path, but the framework clamps it to the badge region.

The first release provides:

- Keyboard navigation between focusable nodes.
- Visible focus indicators.
- Keyboard activation for node and badge actions.
- Touch alternatives for hover, context-menu, and double-click behavior.
- Accessible names for nodes, ports, actions, and interactive badge parts.
- Screen-reader summaries of selection, truncation, pending operations, and
  validation failures.
- Non-pointer alternatives for every required operation.
- Meaning that does not depend on color alone.

ATLAS cannot expose part-level hit geometry. Startup validation rejects a
part-specific handler bound to an ATLAS badge.

## Validation and failure behavior

Validation has two phases because Python cannot inspect browser execution
before the first Components v2 mount.

Python preflight validation is strict by default. It raises before graph
serialization for manifest, package compatibility, schema, binding, handler,
port, image-policy, and transport configuration failures.

Frontend mount validation checks bootstrap registration, asset hash, renderer
API, and required capabilities. The canvas withholds graph rendering when this
phase fails, shows a fatal diagnostic, and sends the same structured diagnostic
to Python. The next callback or rerun raises the corresponding Python error.

An explicit lenient development-preview mode may replace a missing visual with
a neutral diagnostic badge. Production mode never silently substitutes a
missing or incompatible renderer.

A runtime exception in one renderer is isolated to the affected badge and
produces a structured diagnostic. It does not remove the node or stop unrelated
renderers. A manifest, compatibility, or registration failure remains fatal
because the application cannot know which code contract is active.

Every error includes a stable diagnostic code, the responsible canonical kind
or binding when safe, the violated requirement, and a corrective action.

## Observability

The package emits structured Python `logging.LogRecord` objects through the
`streamlit_graph_canvas` logger. It does not install handlers, configure the
root logger, or send telemetry.

This boundary lets the host attach an OpenTelemetry `LoggingHandler`, a
Datadog-compatible JSON formatter, or `ddtrace` log correlation. The host owns
service, environment, trace, span, exporter, sampling, and retention settings.
The integration follows the
[OpenTelemetry Python logging model](https://opentelemetry.io/docs/languages/python/instrumentation/)
and [Datadog Python log collection guidance](https://docs.datadoghq.com/logs/log_collection/python/),
both of which accept Python standard-library log records through host-configured
handlers.

Structured values use `LogRecord.extra` keys with the `sgc_` prefix. Stable
fields cover:

- `sgc_event_code`, `sgc_operation`, and `sgc_status`.
- `sgc_renderer_kind` and `sgc_transport`.
- `sgc_package_version`, `sgc_manifest_version`, and `sgc_renderer_api`.
- `sgc_duration_ms`, `sgc_payload_bytes`, `sgc_node_count`, and
  `sgc_edge_count`.
- `sgc_atlas_key_count`, `sgc_atlas_page_count`, `sgc_atlas_bytes`, and
  `sgc_cache_result`.
- `sgc_topology_revision` and `sgc_presentation_revision`.

The application logging integration may inject vendor-specific service, trace,
and span fields. The library never sets or overwrites those fields.

Default logs exclude labels, badge values, image content, graph payloads, and
complete node IDs. Explicit debug mode may include node and binding IDs and
must warn that these identifiers can contain sensitive application data.

`canvas.explain()` reports renderer resolution, handler routing, transport
selection, and validation decisions without reporting graph payload values.

## Security and privacy considerations

Graph labels, image references, renderer data, and identifiers may be
attacker-controlled. The design maintains these trust boundaries:

- Graph data never selects or loads code.
- Only installed, manifest-declared, explicitly enabled renderer wheels execute
  Python or JavaScript.
- Primitive validation rejects executable markup and external references.
- Remote images use exact application allowlists and server-side materialization.
- Component asset directories contain only public distributable files because
  Streamlit serves every file in those directories.
- Session-scoped atlas caches are the default for private data.
- Logs exclude graph content by default.

Components v2 and enabled JavaScript renderers execute with normal application
page privileges. Shadow DOM is not a security boundary. Applications must
treat an enabled renderer wheel like any other trusted code dependency.

The component provides no authentication or authorization. A host application
that exposes private graph data must provide its own access controls.

## Performance validation

The design treats 2.3 MB per rerun, 50 MB decoded bitmap, and a tenfold payload
reduction as planning assumptions. The beta phase records the dataset,
measurement method, environment, and results for:

- Serialized schema, topology, presentation, primitive, and atlas bytes.
- Initial render and subsequent rerun transfer.
- ELK layout duration.
- Browser scripting, rendering, and memory.
- Mounted elements with viewport culling.
- Atlas unique-key ratio, page bytes, and cache behavior.
- Theme and display-scale transitions.
- Rapid input and action acknowledgment latency.

Failure to reach a tenfold payload reduction does not by itself block `1.0`.
The release report must publish the measured result and explain any difference
from the assumption.

## Implementation plan

### Milestone 0: establish the monorepo and Components v2 spike

Create the two distributions, Apache-2.0 licensing, build tooling, committed
frontend assets, and Windows and Linux continuous integration. Build a thin
Components v2 canvas that proves shadow-DOM mounting, state, triggers, sizing,
and the JavaScript bootstrap registry.

Acceptance criteria:

- Clean wheels install independently on Windows and Linux x86-64.
- The component mounts more than once with stable Streamlit keys.
- A separately built fixture wheel registers a JavaScript renderer through the
  bootstrap registry without Node.js at runtime.
- Conflicting and incompatible registrations fail with stable diagnostics.

### Milestone 1: implement schema and serialization

Implement `GraphData`, schema declarations, explicit edge IDs, multigraphs,
ports, validation, the NetworkX adapter, versioned envelopes, and the combined
element budget. Replace hardcoded frontend node and edge types with schema
lookups.

Acceptance criteria:

- Malformed endpoints, duplicate IDs, undeclared ports, and budget violations
  fail before serialization.
- The same graph round-trips through native `GraphData` and the NetworkX
  adapter without losing multigraph identity.
- Presentation-only changes leave the topology revision unchanged.

### Milestone 2: implement layout and viewport persistence

Add the internal layout-engine boundary, ELK integration, bleed boxes, region
resolution, paint ordering, viewport culling, sizing, position merging, and
`fitView` policies.

Acceptance criteria:

- ELK accounts for every badge region and named port.
- Presentation, selection, resize, and theme changes never start ELK.
- Topology, geometry, schema geometry, and ELK option changes start one full
  layout.
- Positions for surviving nodes persist across Streamlit reruns.

### Milestone 3: implement state, actions, and accessibility

Implement selection modes, viewport state, ordered action triggers,
acknowledgments, deduplication, delegated hit testing, click buffering,
Python-authoritative expand and collapse, and keyboard and touch behavior.

Acceptance criteria:

- Rapid double-click produces one double-click action and no click action.
- Duplicate action delivery invokes a Python handler once per session.
- Delayed, stale, rejected, and duplicate topology operations preserve the
  authoritative graph.
- Automated accessibility checks and manual keyboard tests pass for the stock
  node and badge types.

### Milestone 4: publish the renderer API, PRIMS, and contrib fixtures

Implement manifests, entry-point discovery, explicit enablement, primitive
validation, diagnostics, and renderer API version 1. Build rings, count chip,
gradient strip, avatar, and sparkline renderers in contrib through public APIs.

Acceptance criteria:

- Contrib installs from its built wheel and imports no private core modules.
- PRIMS remain theme-reactive and vector-sharp.
- Part-level hit testing follows renderer declarations.
- Golden images and primitive-validation tests pass.

### Milestone 5: complete JavaScript renderer support

Implement bootstrap lifecycle, page-local registration, scoped shadow-root
rendering, capability checks, conflict handling, and a separately packaged
JavaScript fixture renderer.

Acceptance criteria:

- JavaScript-only renderer wheels install with `pip` and need no runtime Node.js.
- Applications must explicitly enable a renderer before its code executes.
- JavaScript and PRIMS implementations can share one canonical kind and schema
  contract.
- Renderer cleanup does not leak event listeners or DOM nodes across reruns.

### Milestone 6: complete ATLAS

Implement the rasterizer abstraction, provisional `resvg_py` adapter,
deterministic fonts, static SVG serialization, binary page deltas, Blob URLs,
bounded caches, theme variants, resolution buckets, and eviction.

Acceptance criteria:

- Changing a supported binding from PRIMS to ATLAS changes only its transport.
- Live PRIMS and ATLAS golden output match within documented raster tolerance.
- Cache limits hold under high-cardinality badge data.
- Evicted browser pages revoke their Blob URLs.
- Windows and Linux golden tests produce the expected deterministic output.

### Milestone 7: validate the external application and publish beta results

Migrate the Dependency Explorer after core and the renderer ecosystem work as
standalone packages. Use the application as an external conformance fixture,
not as a source dependency.

Acceptance criteria:

- The explorer reproduces its graph through public core and contrib APIs.
- Single-click and double-click behavior matches the documented contract.
- The benchmark report records payload, memory, layout, rendering, and atlas
  results for the representative workload.
- Rollback requires only restoring the explorer's prior dependency and canvas
  integration.

## Test strategy

The repository includes:

- Python unit tests for models, adapters, validation, serialization, revisions,
  renderer discovery, event deduplication, cache bounds, and diagnostics.
- TypeScript unit tests for region resolution, state updates, action queues,
  acknowledgment, hit testing, click buffering, registration, cleanup, and
  layout triggers.
- Property tests that verify bleed containment and serialization invariants.
- Golden-image tests for PRIMS and ATLAS on Windows and Linux x86-64.
- Browser tests for the supported Edge and Chrome matrix.
- Accessibility automation plus documented keyboard, touch, zoom, and
  screen-reader checks.
- Negative security tests for manifests, paths, images, primitives, renderer
  conflicts, and oversized payloads.
- Clean-wheel conformance tests for core, contrib, Python-only, JavaScript-only,
  and combined renderer fixtures.
- External Dependency Explorer integration tests against built distributions.

The test boundary replaces the original proposal's contradictory requirement
to reproduce contrib rendering while contrib is uninstalled. Clean-wheel tests
verify the intended property: contrib and third-party fixtures use only the
published core API.

## Compatibility and release policy

The distributions use semantic versioning. During `0.x`:

- Patch releases remain backward-compatible.
- Breaking Python or schema changes occur only in minor releases and include
  migration notes.
- Deprecations remain for at least one minor release when technically feasible.
- Renderer API version 1 remains stable from the first public beta.

The `1.0` release freezes the supported Python API, schema, serialized event
contract, and renderer API. A later incompatible renderer contract increments
the renderer API major independently of the package major.

Stable `1.0` requires all of the following gates:

- Passing Windows and Linux x86-64 matrices.
- Passing the supported Edge and Chrome browser matrix.
- Dependency Explorer migration through public APIs only.
- Passing PRIMS, JavaScript, and ATLAS conformance suites.
- Passing renderer compatibility and security tests.
- Published beta performance measurements against the planning assumptions.
- Completed API-freeze, migration-documentation, attribution, and packaging
  reviews.
- No unresolved critical or high-severity defects.

## Licensing and release artifacts

Core and contrib use the Apache License 2.0. Bundled dependencies and fonts
retain their own licenses.

The release build generates or verifies `NOTICE`, license inventory, and
distribution metadata from the built wheels and frontend dependency lockfile.
It fails if a shipped dependency or asset lacks recorded attribution.

PyPI publication requires reservation or ownership of
`streamlit-graph-canvas` and `streamlit-graph-canvas-contrib`. Name reservation
is a release prerequisite owned outside this design.

## Alternatives considered

### Keep Components v1

Rejected. Components v2 provides persistent state, transient triggers, package
asset registration, native layout parameters, and lower-overhead integration.
Maintaining both versions would duplicate the most complex state and security
paths.

### Publish core and contrib as one distribution

Rejected for the first release. A separate contrib wheel forces the renderer
contract to work outside core and provides a realistic extension fixture. The
monorepo keeps development overhead bounded.

### Publish `graph-window` immediately

Deferred. One application's traversal semantics are insufficient evidence for
a stable independent package. The project revisits the package after a second
consumer establishes the common contract.

### Use NetworkX as the core graph model

Rejected. A required NetworkX dependency would couple serialization and public
types to an analytics library the canvas does not otherwise need. The optional
adapter preserves convenient integration.

### Load renderer packages by scanning directories

Rejected. Directory scanning has ambiguous ownership, weak diagnostics, and a
larger path-traversal surface. Standard Python distributions, entry points, and
static manifests provide a defined install boundary.

### Install JavaScript renderers through npm at application runtime

Rejected. Production applications should not need Node.js or a frontend build
after `pip install`. A Python wheel can contain the prebuilt self-contained ES
module and its manifest.

### Evaluate JavaScript source or fetch remote renderer modules

Rejected. Both choices expand the code-loading boundary and complicate content
security policy. Package-based Components v2 bootstrap registration loads only
installed assets.

### Make ATLAS the default transport

Rejected. ATLAS performs well when many nodes share visual states and poorly
when key cardinality approaches node count. It also gives up vector sharpness
and part-level hit geometry. Applications choose it per binding.

### Keep public atlas URLs or generated static assets

Rejected. Public asset locations risk cross-session disclosure and unbounded
storage. Binary Components v2 deltas, session caches, and Blob URLs keep
generated data scoped to the application session by default.

### Accept raw SVG renderers

Deferred. Raw SVG adds sanitization and versioning risk without a demonstrated
gap in the primitive vocabulary. A future proposal must define a strict
allowlist-based sanitizer.

### Let the browser mutate topology

Rejected. Competing Python and browser graph states produce stale updates and
reconnection errors. Python-authoritative revisions make reruns and duplicate
actions deterministic.

### Accept application-provided positions now

Deferred. ELK-only behavior keeps the first release testable. The internal
layout boundary and position-independent public data model preserve a path to
add authoritative positions later.

## Trade-offs and risks

### Three transports increase the first-release surface

PRIMS, JavaScript, and ATLAS require separate runtime and test paths. Their
shared kind, region, options, data, and event contracts reduce divergence. A
transport that cannot pass the common conformance suite must not ship.

### JavaScript renderers are a supply-chain boundary

Explicit enablement prevents graph data from selecting code, but it cannot make
enabled JavaScript safe. Documentation, manifest hashes, package review, and
dependency controls mitigate accidental loading. They do not sandbox malicious
code.

### The bootstrap registry depends on Components v2 lifecycle behavior

The milestone 0 spike must prove registration order, cleanup, reruns, multiple
canvas instances, and page navigation before the project freezes renderer API
version 1. If the spike fails, the design must revisit first-release JavaScript
extensibility rather than hide the failure behind source evaluation.

### PRIMS can create large SVG trees

Viewport culling limits mounted work, and ATLAS provides an explicit option for
highly duplicated complex badges. Beta measurements determine practical
guidance by renderer and workload.

### ATLAS can consume more memory than inline images

High key cardinality and large surround regions can make atlases inefficient.
Bounded caches, cardinality diagnostics, resolution buckets, and per-binding
transport selection contain the risk.

### Bleed boxes change visible spacing

ELK sizes the full bleed box rather than the opaque node body. Minimap scale,
fit padding, and graph density require visual tuning after regions are enabled.

### Strict startup validation rejects partially configured applications

Strict failure makes version and transport errors visible before users interact
with the graph. The explicit lenient development mode supports previews without
changing production behavior.

### The default budget may not fit every graph

The combined 700-element budget is a safe planning default, not a performance
guarantee. Applications can override it after measuring their schemas,
renderers, and target browsers.

## Rollout and rollback

The project publishes `0.x` beta wheels after milestones 0 through 6 pass their
acceptance criteria. The Dependency Explorer then pins those wheels and runs the
external conformance and benchmark phase.

Each milestone retains a standalone example and a working public vertical
slice. The Dependency Explorer keeps its prior canvas integration until the
replacement passes its acceptance tests. Rolling back the application restores
the prior dependency pin and integration path.

Package rollback uses a previous compatible wheel. Renderer manifests and
serialized envelopes reject incompatible combinations instead of attempting a
silent downgrade.

## Open questions and release prerequisites

- `TODO(pypi-reservation)`: Reserve or confirm ownership of the two standardized
  PyPI distribution names before publication.
- `TODO(stock-font)`: Select the exact open-licensed sans-serif font that core
  and contrib package for deterministic ATLAS rendering and record its license.
- `TODO(beta-dataset)`: Freeze the representative Dependency Explorer dataset
  and benchmark procedure before beta performance validation.
- `TODO(atlas-validation)`: Confirm the provisional `resvg_py` version range and
  golden-image tolerance on the Windows and Linux release matrix.
