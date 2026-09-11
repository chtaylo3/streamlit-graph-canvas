# Static sprite atlas implementation plan

Status: implementation plan for `feat/static-sprite-atlas`.

This plan turns the existing one-raster-per-page beta implementation into a
real, bounded sprite atlas and adds a first-class way for applications to map
static transparent PNG images to nodes. It also separates server-side PRIMS
rasterization from atlas packing so both renderer-generated rasters and
application-provided images can use the same page, delta, cache, and browser
cropping machinery.

## Goals

- Let an application provide a consolidated catalog of named PNG images and
  reference those names from nodes without placing paths or image bytes in graph
  data.
- Preserve PNG alpha transparency.
- Require a light/default image for every catalog entry and allow an optional
  dark-theme image.
- Resolve a dark-theme request to the dark image when present and otherwise
  fall back deterministically to the light image.
- Pack multiple normalized images into bounded PNG pages and serialize page
  coordinates with each node sprite reference.
- Make the browser crop the correct rectangle from the packed page.
- Reuse the existing content-addressed page deltas, Blob URL lifecycle, CSP,
  session/tenant isolation, DPR buckets, and fail-closed limits.
- Let PRIMS-derived raster output use the same packer.
- Correct the public terminology before a stable release while providing a
  migration path from the `0.1.0rc1` API.

## Non-goals for the first increment

- Remote image fetching.
- SVG, JPEG, WebP, GIF, animation, or video sources.
- User-supplied prepacked atlas coordinates or arbitrary atlas pages.
- Runtime image URLs or filesystem paths in the browser envelope.
- Interactive subparts inside a sprite.
- A globally shared cache for private application assets.
- Optimal bin packing. Determinism, safety, and stable deltas take precedence
  over maximum packing density.

## Terminology and compatibility

The current `Transport.ATLAS` behavior is server-side rasterization of a PRIMS
renderer followed by a one-tile PNG cache. Rename that public behavior to
`Transport.RASTER` and describe it as the **raster transport**.

Use atlas terminology only for the shared packed-page delivery layer:

- `RasterTile`: one normalized or generated RGBA image before packing.
- `RasterTileCache`: cache of renderer-produced tiles, replacing the current
  conceptual role of `AtlasCache`.
- `AtlasPage`: a PNG containing one or more sprites.
- `SpriteLocation`: page ID, crop rectangle, logical size, and resolution.
- `AtlasPageCache`: bounded cache of immutable packed pages and sprite mappings.
- `SpriteCatalog`: application-provided named static images.

Because `Transport.ATLAS`, `AtlasPolicy`, `AtlasScope`, and `AtlasCache` shipped
in `0.1.0rc1`, retain documented compatibility aliases during the remaining
0.1 prereleases where practical. Emit deprecation warnings only from direct
public construction or use, never once per node. Remove aliases no earlier than
the next declared breaking API boundary. If an alias cannot be implemented
without ambiguous behavior, document the release-candidate break explicitly.

The serialized envelope must use a new codec version. Do not make an older
frontend silently interpret packed coordinates as one-tile pages.

## Proposed public API

Add immutable public models along these lines; exact spelling may be adjusted
to match existing project conventions, but retain the semantic separation.

```python
from pathlib import Path

from streamlit_graph_canvas import (
    PngImage,
    SpriteBinding,
    SpriteCatalog,
    SpriteRef,
    StaticSprite,
)

sprites = SpriteCatalog(
    {
        "repository:healthy": StaticSprite(
            light=PngImage.from_file(Path("images/healthy-light.png")),
            dark=PngImage.from_file(Path("images/healthy-dark.png")),
        ),
        "repository:warning": StaticSprite(
            # Light is mandatory and is also the dark fallback.
            light=PngImage.from_file(Path("images/warning.png")),
        ),
    }
)
```

`PngImage` must own immutable bytes after construction. `from_file()` reads the
trusted application path on the server immediately; the path is not retained
as browser-visible data. Also provide `PngImage.from_bytes()`.

Declare sprite placement on a node type independently of renderer discovery:

```python
NodeType(
    "repository",
    sprites=(
        SpriteBinding(
            name="thumbnail",
            region=Region.at(8, 8, 72, 72),
            layer="under",
            z=0,
            fit="contain",
            required=False,
        ),
    ),
)
```

Reference a catalog entry from a node:

```python
Node(
    "repo-a",
    "repository",
    "Repository A",
    sprites={
        "thumbnail": SpriteRef(
            "repository:warning",
            accessible_text="Warning dependency summary",
        )
    },
)
```

Pass the catalog explicitly to both validation/serialization and the mounted
component:

```python
graph_canvas(graph, schema, key="dependencies", sprite_catalog=sprites)
```

`SpriteBinding` should reuse the existing region, `under`/`over` layer, and
z-order semantics. Keep it separate from `BadgeBinding`: a static image is not
a renderer package and should not require `enable_renderers()` or a fabricated
renderer kind. The serializer may normalize badges and sprites into one ordered
paint-layer representation for the frontend.

Supported initial fit policies:

- `contain` (default): preserve aspect ratio and show the full image.
- `cover`: preserve aspect ratio and crop to fill the region.
- `fill`: scale independently in each dimension.

The binding region is the logical display box. Atlas coordinates are physical
pixels and must never alter node layout dimensions.

## Theme contract

Every `StaticSprite` has:

- `light`: required and treated as the default variant.
- `dark`: optional.

Resolution rules:

1. In light mode, use `light`.
2. In dark mode, use `dark` when supplied.
3. In dark mode without `dark`, use `light` without error or warning.
4. A theme change must not change topology or trigger layout.
5. Both variants use the same binding region and fit policy, even when their
   source dimensions differ.
6. Deduplication is content based, so identical light and dark images occupy
   only one sprite.

Retain the existing browser theme state and lazy theme behavior for the first
increment: the browser reports `light` or `dark`; Python selects and sends the
active variant; a change causes a presentation-only rerun. The frontend should
retain the previous valid sprite until the selected variant page is available,
then swap atomically. It must not briefly show a missing-image icon.

Document that light is the deterministic initial/default theme. A later,
separately measured enhancement may send both variants and switch entirely in
the browser, but doubling initial image payload must not be the default without
evidence.

Renderer-generated raster tiles continue to include the resolved palette and
theme in their content key. Static sprites include the selected variant's
normalized content hash, fit policy, logical size, and resolution bucket in the
tile key.

## PNG ingestion and normalization

Create a dedicated image normalization module rather than adding more duties to
the current `atlas.py`.

For every `PngImage`:

1. Enforce a bounded encoded-byte limit before decode.
2. Verify PNG signature and IHDR dimensions.
3. Use the supported Pillow range already enforced by the atlas extra.
4. Enable Pillow decompression-bomb protections and turn limit warnings into
   actionable validation failures.
5. Fully decode the image and reject truncation, animation, multiple frames,
   and any non-PNG actual format.
6. Enforce width, height, and decoded-pixel limits.
7. Convert to canonical straight-alpha RGBA.
8. Strip metadata and ancillary chunks by deterministic re-encoding.
9. Preserve transparent pixels.
10. Hash the normalized content plus dimensions and normalizer revision.

Errors must identify the catalog key through a bounded subject but must not
include image bytes or sensitive filesystem paths. Catalog IDs must be bounded,
non-empty stable strings and duplicates must fail before serialization.

Validate the complete catalog working set, including limits for entry count,
aggregate encoded bytes, and aggregate decoded pixels. Continue to default to
session isolation. Tenant scope must use the authenticated server-derived
tenant identifier already required by the package.

## Raster tile preparation

Normalize both source paths into one internal type:

```text
PRIMS renderer -> deterministic Pillow rasterizer --+
                                                    +-> RasterTile
StaticSprite active PNG -> normalize/resize/crop ---+
```

Prepare a tile at the binding's logical size multiplied by the current DPR
bucket. Apply `contain`, `cover`, or `fill` during tile preparation so atlas
cropping itself remains a simple rectangle operation. For `contain`, unused
pixels remain transparent.

The tile content key must contain:

- source normalized hash;
- normalizer/rasterizer revision and supported Pillow identity;
- logical width and height;
- resolution bucket;
- fit policy;
- selected theme variant where it affects the source;
- renderer kind/version/options/data/palette for PRIMS-derived tiles.

Do not include node ID. Nodes with identical effective images and geometry must
share a tile and atlas location.

## Deterministic atlas packing

Implement a bounded deterministic shelf packer first.

- Deduplicate tiles by content key before packing.
- Sort a new batch deterministically by height descending, width descending,
  then content hash.
- Use fixed bounded page dimensions selected by policy.
- Leave at least one transparent padding pixel at the target DPR around every
  tile. Consider edge extrusion only if browser tests demonstrate interpolation
  bleed; transparent thumbnails should not gain opaque borders by default.
- Reject a tile that cannot fit an empty page before modifying cache state.
- Produce integer physical-pixel coordinates.
- Assert that every rectangle is within its page and that padded rectangles do
  not overlap.

Use immutable packed batches for stable deltas:

1. Reuse every cached tile-to-location mapping still available.
2. Collect all required uncached tiles for the current serialization.
3. Pack that missing batch into one or more pages.
4. Freeze and content-address those pages.
5. Send later additions in new immutable pages rather than mutating an existing
   content-addressed page.

This trades some packing density for stable page IDs, stable coordinates, and
small rerun deltas. Do not repack the full working set merely because one node
or image was added.

Eviction operates on complete pages. A page is protected while any sprite in
the current graph references it. If the active page working set cannot fit,
fail before emitting a partial presentation, as the current implementation
does.

## Policy model

Split limits that currently conflate tiles and pages. The reviewed policy must
cover at least:

- maximum source bytes per image;
- maximum source decoded pixels per image;
- maximum catalog entries;
- maximum catalog aggregate bytes/pixels;
- maximum prepared tile pixels;
- atlas page width, height, decoded pixels, and encoded bytes;
- padding;
- aggregate and per-tenant page count and bytes;
- supported DPR buckets.

Keep conservative hard ceilings in the generated cross-language contract.
Browser validation must independently enforce page byte, PNG signature,
declared dimensions, decoded-pixel, digest, page-count, and aggregate-byte
limits.

## Serialization contract

Bump `CODEC_VERSION` and update the generated TypeScript contract.

Atlas page deltas retain:

```json
{
  "pageId": "...",
  "contentSha256": "...",
  "mediaType": "image/png",
  "base64": "...",
  "width": 512,
  "height": 512
}
```

Each resolved sprite contains:

```json
{
  "name": "thumbnail",
  "layer": "under",
  "z": 0,
  "region": {"x": 8, "y": 8, "width": 72, "height": 72},
  "fit": "contain",
  "accessibleText": "Warning dependency summary",
  "sprite": {
    "pageId": "...",
    "x": 98,
    "y": 194,
    "width": 144,
    "height": 144,
    "resolution": 2.0
  }
}
```

Coordinates and sprite dimensions are physical pixels within the page. Region
dimensions are logical CSS/SVG units. Validate all coordinates on both sides:
positive dimensions, non-negative origin, safe integers, supported resolution,
and rectangle fully contained in the declared page.

Keep page bytes outside topology and presentation hashes. Sprite mappings and
selected theme belong to presentation, never topology.

## Browser rendering and cache changes

Change `BrowserAtlasCache` to retain a descriptor rather than only URL/bytes:

```ts
type CachedPage = {
  url: string;
  bytes: number;
  width: number;
  height: number;
};
```

Render a sprite by clipping its atlas page to the serialized rectangle. Either
an SVG viewBox over the physical page coordinates or an explicit clip path is
acceptable, provided tests prove exact crop behavior at every DPR bucket.

Requirements:

- Use the page's actual dimensions, not the binding region, for the `<image>`.
- Honor `x` and `y`; the current frontend ignores them.
- Scale the selected crop into the logical binding region.
- Honor `contain`, `cover`, and `fill` as already baked into the tile; the atlas
  stage itself must not distort the crop.
- Preserve alpha.
- Keep images non-interactive and `aria-hidden`; include `accessibleText` in the
  containing node's accessible name, following the existing badge-summary
  pattern.
- Protect every page referenced by either the displayed sprite or the previous
  sprite retained during an atomic theme transition.
- Revoke Blob URLs only after no mounted canvas lease uses them.
- Continue to require only `blob:` in `img-src`; no data, remote-image, worker,
  or Blob-script permission is introduced.

## Refactoring map

Suggested source organization:

- `images.py`: `PngImage`, `StaticSprite`, `SpriteCatalog`, normalization.
- `sprites.py`: `SpriteRef`, `SpriteBinding`, prepared tile models.
- `raster.py`: PRIMS rasterization and renderer tile keys.
- `atlas.py`: packing, immutable pages, mappings, policy, page cache, tenant
  manager.
- `serialization.py`: orchestration only; resolve bindings, request tiles,
  collect mappings/deltas, and construct the envelope.
- `frontend/src/atlas-cache.ts`: validated page cache and leases.
- `frontend/src/index.tsx` or a focused `sprite.tsx`: cropping and theme-safe
  rendering.

Avoid leaving all logic in `serialization.py`. The serializer should depend on
small validated services whose behavior is independently unit tested.

## Tests and acceptance criteria

### Python unit tests

- Light image is required.
- Dark image is optional.
- Light mode selects light.
- Dark mode selects dark when present.
- Dark mode falls back to light when absent.
- Identical light/dark content deduplicates.
- Alpha survives normalization, resizing, packing, and PNG encoding.
- Paths never appear in the envelope, diagnostics, content IDs, or logs.
- Invalid signature, malformed PNG, truncation, multiple frames, oversized
  bytes, dimensions, decoded pixels, and decompression bombs fail closed.
- Same bytes normalize identically across supported environments.
- Duplicate content used by multiple nodes shares one location.
- Mixed image dimensions pack without overlap and remain in bounds.
- Packing order and page bytes are deterministic.
- Adding a later image does not move an already cached sprite.
- Page eviction removes every mapping owned by the page.
- An active page cannot be evicted; an oversized working set fails atomically.
- Session and tenant isolation remain intact.
- PRIMS-derived raster tiles and static images can coexist on one atlas page.
- Theme changes affect presentation hash/revision but not topology.
- Compatibility aliases behave as documented.

### TypeScript unit tests

- Page dimensions and digests are validated before cache mutation.
- Invalid or out-of-page sprite rectangles fail closed.
- Cropping uses non-zero `x` and `y` correctly.
- 1x, 1.5x, and 2x mappings display at identical logical dimensions.
- Blob URLs are reused and revoked under the existing lease guarantees.
- A stale asynchronous page delta cannot replace current state.
- Theme transition retains the previous sprite until the replacement exists.

### Browser/conformance tests

- A page visibly contains at least two distinct transparent sprites.
- Two nodes crop different regions from the same Blob URL.
- Pixel/screenshot checks prove no neighboring-sprite bleed.
- Light mode displays the light image.
- Dark mode displays the supplied dark image.
- Dark mode displays the light fallback when no dark image exists.
- Switching the emulated color scheme changes presentation without relayout.
- Multiple canvases cannot revoke each other's pages.
- Strict CSP reports no violations and no external image requests.
- A clean installed wheel contains all frontend changes and needs no runtime
  Node.js.

### Performance evidence

Add a representative workload using 500 nodes and record:

- number of unique source images and deduplicated tiles;
- atlas page count and fill ratio;
- initial encoded page bytes;
- rerun delta bytes with no change;
- delta bytes after one new or changed image;
- browser decoded image memory estimate;
- Blob URL count compared with the one-tile implementation;
- serialization, packing, and browser render time.

Do not claim a performance improvement until these measurements are recorded.

## Documentation updates

- Update the README installation extra and examples using the project's chosen
  package-manager conventions.
- Explain raster transport versus atlas delivery.
- Add a static sprite quick start with transparent PNGs and theme variants.
- Document light-required/dark-optional fallback behavior.
- Update CSP, multi-tenancy, image security, renderer authoring, architecture,
  beta-contract, and conformance documents.
- State that static sprites do not require renderer discovery or enablement.
- Explain that changing catalog contents may change presentation and page
  deltas but not topology/layout.
- Remove or revise every statement that pages currently contain one tile once
  packing ships.

## Delivery sequence

1. Introduce terminology aliases, public sprite models, and validation without
   changing browser behavior.
2. Extract the existing rasterizer and tile cache responsibilities.
3. Implement PNG normalization and theme selection.
4. Implement deterministic immutable-batch packing and page mappings.
5. Bump the codec and update Python serialization.
6. Implement frontend coordinate validation and cropping.
7. Route PRIMS raster output through the packer.
8. Complete unit, clean-wheel browser, CSP, multi-canvas, and performance tests.
9. Update all public documentation and generated artifacts.
10. Run the full release gate and inspect built wheel/sdist contents before
    preparing the next release candidate.

## Definition of done

The feature is complete when an application can provide multiple named
transparent PNGs, including light/default and optional dark variants; assign
them to nodes; observe multiple images packed into shared content-addressed
pages; and verify that every node displays only its assigned crop at all
supported DPR buckets and themes. All bounds, tenant isolation, CSP behavior,
Blob URL lifecycle, accessibility, deterministic builds, clean-wheel tests, and
release gates must remain green.
