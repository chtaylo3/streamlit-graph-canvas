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
| ATLAS transport | Built | Pillow-backed deterministic PNG pages, content-addressed deltas, Blob URL lifecycle, theme/DPR variants, and bounded session or tenant caches |
| Images, bleed sizing, and region helpers | Deferred | The beta does not promise image transport, bleed-driven layout, or the full region helper vocabulary |
| Observability | Partial | Internal `streamlit_graph_canvas` logging uses selected `sgc_` fields; the complete proposed field set and `canvas.explain()` are not stable beta APIs |
| Performance caching | Partial | Verified manifest metadata may be cached; renderer-output caching waits for reproducible benchmarks and a purity/memory contract |
| CSP | Built and browser-tested | JavaScript requires same-origin scripts; ATLAS adds Blob images; the complete Streamlit host policy is tested in Chromium |

## Protocol v1

Protocol v1 is deliberately limited to node clicks. Each action contains a
canonical UUID operation ID, a positive JavaScript-safe sequence, the current
topology revision, authoritative node ID/type, node target, and boolean
keyboard modifiers. Python validates the complete shape, ignores already
acknowledged actions, and discards otherwise valid actions for stale or unknown
topology. Malformed envelopes fail closed with a diagnostic.

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

## Compatibility policy

- Python 3.12, 3.13, and 3.14 are tested on Windows and Linux.
- Streamlit 1.62 is the minimum; CI tests the minimum and the current locked
  version. A scheduled lane tests the newest prerelease without blocking normal
  development.
- The clean-wheel browser gate uses pinned Chromium on Ubuntu and tests
  core-only, stock contrib, and hostile-fixture environments.
- Node.js 24 is the frontend build target.
- Firefox, WebKit, and ARM64 remain best-effort. JavaScript and ATLAS are in the
  clean-wheel Chromium release matrix.

An upper Streamlit dependency bound is added only for a demonstrated
incompatibility. Known-bad versions must instead produce an actionable runtime
diagnostic and be excluded by the release compatibility policy.

## Security and CSP behavior

All executable assets are wheel-packaged and same-origin. JavaScript renderer
factories are trusted page-level code; ATLAS creates only PNG Blob URLs. Neither
transport performs a runtime third-party fetch. Shadow DOM is style isolation,
not a security sandbox. Enabled Python and JavaScript renderers must be reviewed
like any other dependency.

See `transports-and-csp.md` for the tested policy, the distinction between host
and transport allowances, tenant-cache requirements, and deployment guidance.
