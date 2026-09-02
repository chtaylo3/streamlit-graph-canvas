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
| Topology/presentation revisions | Built | Presentation-only changes do not change topology identity or rerun ELK |
| ELK layout | Built | Framework-owned initial/topology layout; application positions remain deferred |
| Selection and viewport | Built for beta | Persistent across component remounts; removed nodes are reconciled; viewport commits at interaction end |
| Fit view | Built for beta | `never`, `initial`, and `topology-change` have distinct behavior; a restored viewport takes precedence over initial fitting |
| Action protocol | Built, intentionally narrow | Protocol v1 contains ordered, acknowledged, topology-validated node `click` actions only |
| Other gestures and handlers | Deferred | Double-click, context menu, expand/collapse, badge activation, handler routing, and click buffering require a future protocol version |
| Node and edge styling | Built for beta | Symbolic palette tones control node fill/stroke/text/radius and edge stroke/width/dash |
| Named ports | Built for beta | Declared ports are rendered and edge source/target handles are honored |
| Accessibility | Built for beta with release checks | Named keyboard-operable nodes, visible focus, accessible badge text summaries, controls, and automated Chromium checks |
| Renderer discovery | Built | Import-free discovery, requested-only validation, explicit enablement, distribution-owned implementation imports, and diagnostics for malformed installed packages |
| PRIMS transport | Built | Closed rectangle/circle/text vocabulary with bounded output and theme-aware palette resolution |
| JavaScript renderer transport | Built | Explicitly enabled, hash-bound Components v2 bootstraps register trusted scoped-SVG factories; conflicts and missing registrations fail closed |
| Raster transport | Built | `Transport.RASTER` runs validated Python PRIMS through Pillow and the shared packed-page delivery path; legacy `Transport.ATLAS` compatibility remains for the 0.1 release-candidate series |
| Static PNG sprites | Built | Explicit catalogs map stable IDs to required light/default and optional dark PNGs; dark falls back to light, alpha is preserved, and paths/source bytes never enter the browser envelope |
| Atlas delivery | Built | Deterministic immutable pages contain one or more static or procedural raster tiles; node layers carry real crop coordinates, and page deltas use bounded session or tenant caches and Blob URL lifecycle management |
| Other images, bleed sizing, and region helpers | Deferred | Remote sources, SVG, JPEG, WebP, animation, user-provided prepacked pages, bleed-driven layout, and the full region helper vocabulary are outside this beta contract |
| Observability | Partial | Internal `streamlit_graph_canvas` logging uses selected `sgc_` fields; the complete proposed field set and `canvas.explain()` are not stable beta APIs |
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
multi-sprite pages, tenant/session isolation, page deltas, and browser crop
validation. A selected theme, resolution, sprite mapping, or page delta changes
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

## Security and CSP behavior

All executable assets are wheel-packaged and same-origin. JavaScript renderer
factories are trusted page-level code; raster and static sprite delivery create
only PNG Blob URLs. Neither path performs a runtime third-party fetch. Static
PNG source paths and bytes remain on the server. Shadow DOM is style isolation,
not a security sandbox. Enabled Python and JavaScript renderers must be reviewed
like any other dependency.

See `transports-and-csp.md` for the tested policy, the distinction between host
and transport allowances, tenant-cache requirements, and deployment guidance.
