# JavaScript, ATLAS, multi-tenancy, and CSP

The canvas supports PRIMS, trusted JavaScript, and ATLAS transports per badge
binding. Graph data cannot select a package or executable asset. Every renderer
must be installed, hash-verified, and explicitly enabled by the application.

## Trusted JavaScript transport

A JavaScript renderer wheel packages a Components v2 bootstrap, declares its
component key and entry file in `renderer.toml`, and hashes the same file in
`assets`. Core validates that the component manifest, component asset directory,
entry, renderer asset, distribution, version, and hash all agree before mounting
the bootstrap.

The bootstrap registers factories in the page-local
`Symbol.for("streamlit-graph-canvas.renderers.v1")` registry. Registration is
idempotent only for an exact kind, renderer API, package version, and generated
build identity;
conflicts and missing registrations fail the canvas mount. The canvas passes raw
validated JSON data, static options, resolved symbolic palette values, and one
scoped SVG element to the factory. Cleanup runs at badge unmount. Core never
evaluates source strings, imports runtime npm packages, creates executable Blob
URLs, or fetches code from another origin.

This is a supply-chain boundary, not a sandbox. Enabled JavaScript has normal
page privileges even though the target SVG and component styles live in a shadow
root. Changing the enabled renderer set requires a page reload.

## ATLAS transport and multi-tenancy

ATLAS runs the same validated Python PRIMS renderer, resolves a literal light or
dark palette, rasterizes the closed primitive vocabulary to lossless PNG, and
uses content-addressed page deltas. The browser creates Blob URLs only for PNG
pages, reuses known page IDs, and revokes URLs on server eviction. ATLAS supports
1x, 1.5x, and 2x device-scale buckets; the browser reports theme and scale as
persistent state.

`AtlasPolicy` applies aggregate page/byte, per-tenant page/byte, decoded-pixel,
and encoded-page limits. Session scope is the private-data default. Tenant scope
is an explicit opt-in:

```python
from streamlit_graph_canvas import AtlasPolicy, AtlasScope, graph_canvas

result = graph_canvas(
    graph,
    schema,
    key="dependencies",
    renderer_registry=registry,
    atlas_policy=AtlasPolicy(
        scope=AtlasScope.TENANT,
        max_pages=256,
        max_bytes=64 * 1024 * 1024,
        max_tenant_pages=64,
        max_tenant_bytes=16 * 1024 * 1024,
    ),
    atlas_tenant=authenticated_tenant_id,
)
```

The process cache keys every entry and page identity by tenant; it never returns
another tenant's page. A tenant ID is required for tenant scope and is not sent
to the browser. Limits use a locked LRU and fail closed if the current graph's
working set cannot fit, preventing eviction from producing partial output.
Applications must derive `atlas_tenant` from authenticated server-side identity,
not request parameters supplied without authorization.

Pillow `>=12.3,<13` is the supported internal beta rasterizer range and is
available through `streamlit-graph-canvas[atlas]`. ATLAS fails closed at runtime
outside that range, including when the installed version is malformed. Every
content key includes the normalized Pillow version and the graph-canvas
rasterizer revision, so caches cannot be reused across rasterizer changes. Its
deterministic embedded bitmap font is used; browser-only `var(--st-*)` palette
values are rejected for ATLAS, so ATLAS bindings must provide literal light and
dark colors for every emitted tone.

## Content Security Policy

The transport-specific additions are deliberately narrow:

- JavaScript: `script-src 'self'`; no remote, `data:`, Blob script, or
  `unsafe-eval` requirement.
- ATLAS: add `blob:` to `img-src`; ATLAS does not require Blob scripts, workers,
  remote images, or network fetches.

`required_csp_directives()` returns these additive transport requirements.
`streamlit_host_csp(..., app_origin="https://canvas.example")` returns the full,
origin-specific policy exercised through the Chromium reverse-proxy
conformance deployment. Passing an origin replaces scheme-wide WebSocket
sources with the one corresponding `ws://` or `wss://` origin. The optional
`frame_ancestors` argument accepts only `'self'`, `'none'`, or exact HTTP(S)
origins; wildcard, credential-bearing, path, query, and fragment sources are
rejected. Use `frame_ancestors=("'none'",)` for deployments that must never be
framed:

```text
default-src 'self';
script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
connect-src 'self' wss://canvas.example;
font-src 'self' data:;
object-src 'none';
base-uri 'none';
form-action 'self';
frame-ancestors 'self';
manifest-src 'self';
media-src 'self';
worker-src 'self'
```

`'unsafe-inline'`, `'wasm-unsafe-eval'`, `data:` fonts, and WebSocket sources are
requirements observed for the enclosing Streamlit runtime, not added by the two
renderer transports. The CSP must be set as an HTTP response header by the host
or reverse proxy; a component cannot weaken or replace its page's policy.

The clean-wheel Chromium matrix runs Streamlit behind an HTTP/WebSocket reverse
proxy that sets this response header, records every
`securitypolicyviolation`, blocks unexpected external requests, and verifies
both a packaged JavaScript-only renderer and Blob-backed ATLAS output.
