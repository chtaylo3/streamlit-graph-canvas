# JavaScript, raster and sprite delivery, multi-tenancy, and CSP

The canvas supports PRIMS, trusted JavaScript, and raster transports per badge
binding. It also accepts application-provided static PNG sprites through a
separate catalog and binding API. Graph data cannot select a package,
executable asset, filesystem path, or image bytes. Every renderer must be
installed, hash-verified, and explicitly enabled by the application; static
sprites do not require renderer discovery or enablement.

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

## Raster transport and atlas delivery

`Transport.RASTER` runs the same validated Python PRIMS renderer as the vector
transport, resolves a literal light or dark palette, and rasterizes the closed
primitive vocabulary to a lossless PNG tile. It accurately names the
procedural operation that the 0.1.0rc1 API called `Transport.ATLAS`. The legacy
name remains compatibility behavior during the 0.1 release-candidate series;
new bindings and renderer manifests should declare `raster`.

Raster transport is distinct from atlas delivery. Static PNGs and procedural
raster tiles both enter the same deterministic packer. Missing tiles are
deduplicated, ordered deterministically, and placed into immutable PNG pages
with transparent padding. A page can contain multiple tiles. Each resolved
node layer carries a physical `x`, `y`, `width`, and `height`, and the browser
crops that real rectangle from the shared page into the binding's logical
region. Existing pages are not repacked when a later tile is introduced, which
keeps page IDs and mappings stable across reruns.

The browser creates Blob URLs only for validated PNG pages, reuses known page
IDs, and revokes URLs on server eviction after active canvas leases release
them. Atlas delivery supports 1x, 1.5x, and 2x device-scale buckets; the browser
reports theme and scale as persistent state. Renderer-generated tiles and
static sprites share page deltas, crop validation, Blob URL lifecycle, and
cache isolation.

### Static sprite catalog

Static sprites are explicitly supplied by the application:

```python
from pathlib import Path

from streamlit_graph_canvas import (
    Node,
    NodeType,
    PngImage,
    Region,
    SpriteBinding,
    SpriteCatalog,
    SpriteRef,
    StaticSprite,
)

catalog = SpriteCatalog(
    {
        "warning": StaticSprite(
            light=PngImage.from_file(Path("images/warning-light.png")),
            dark=PngImage.from_file(Path("images/warning-dark.png")),
        ),
        "healthy": StaticSprite(
            light=PngImage.from_file(Path("images/healthy.png")),
        ),
    }
)

node_type = NodeType(
    "service",
    sprites=(
        SpriteBinding(
            "thumbnail",
            Region.at(8, 8, 72, 72),
            fit="contain",
        ),
    ),
)
node = Node(
    "api",
    "service",
    "API",
    sprites={"thumbnail": SpriteRef("warning", accessible_text="Warning status")},
)
```

Pass `sprite_catalog=catalog` to `graph_canvas(graph, schema, key=...)` or
`serialize_graph(schema, graph, ...)`. The light image is required and is the
deterministic default. The dark image is optional: dark mode selects it when
present and otherwise falls back to light without error or warning. Different
variant dimensions do not change the binding region. Theme and page changes
affect presentation only and never topology or ELK layout.

`PngImage.from_file()` reads a trusted server path immediately; it does not
retain the path as browser-visible data. `PngImage.from_bytes()` owns a copy of
the supplied bytes. Source paths and source image bytes never enter graph data
or the component envelope. Images are fully decoded, normalized to canonical
RGBA, stripped of metadata, deterministically re-encoded, and content-hashed
before packing. Alpha transparency is preserved.

`SpriteBinding.fit` accepts:

- `contain` (default), which preserves aspect ratio and shows the whole image
  with transparent unused space;
- `cover`, which preserves aspect ratio and center-crops to fill the region;
- `fill`, which scales independently in each dimension.

The first static-image contract accepts only complete, single-frame PNGs. It
does not fetch remote URLs or accept SVG, JPEG, WebP, GIF, animation, video,
caller-provided atlas pages, or caller-provided crop coordinates.

### Isolation and limits

`AtlasPolicy` applies encoded bytes and decoded dimensions per source image;
catalog entry, aggregate-byte, and aggregate-pixel limits; prepared-tile
pixels; atlas page dimensions, pixels, padding, and encoded bytes; and aggregate
and per-tenant page/byte limits. All limits fail closed before a partial
presentation is emitted. Session scope is the private-data default. Tenant
scope is an explicit opt-in:

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

The process cache keys every tile mapping, page, and page identity by tenant; it
never returns another tenant's page. A tenant ID is required for tenant scope
and is not sent to the browser. Limits use a locked LRU and fail closed if the
current graph's working set cannot fit, preventing eviction from producing
partial output. Applications must derive `atlas_tenant` from authenticated
server-side identity, not request parameters supplied without authorization.

Pillow `>=12.3,<13` is the supported internal beta rasterizer range and is
available through `streamlit-graph-canvas[atlas]`. Raster and static sprite
processing fail closed at runtime outside that range, including when the
installed version is malformed. Every tile content key includes the normalized
Pillow version and the applicable normalizer or rasterizer revision, so caches
cannot be reused across incompatible processing changes. The procedural
rasterizer uses its deterministic embedded bitmap font; browser-only
`var(--st-*)` palette values are rejected for raster bindings, which must
provide literal light and dark colors for every emitted tone.

## Content Security Policy

The transport-specific additions are deliberately narrow:

- JavaScript: `script-src 'self'`; no remote, `data:`, Blob script, or
  `unsafe-eval` requirement.
- Raster and static sprites: add `blob:` to `img-src`; atlas delivery does not
  require Blob scripts, workers, remote images, `data:` image sources, or
  network fetches.

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
both a packaged JavaScript-only renderer and Blob-backed packed raster/static
sprite output.
