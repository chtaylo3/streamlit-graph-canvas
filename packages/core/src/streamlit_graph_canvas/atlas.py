"""Bounded, content-addressed raster atlas cache for PRIMS renderers."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from . import telemetry
from .contract import (
    MAX_ATLAS_AGGREGATE_BYTES,
    MAX_ATLAS_DECODED_PIXELS,
    MAX_ATLAS_PAGE_BYTES,
    MAX_ATLAS_PAGES,
    MAX_PREPARED_TILE_DECODED_PIXELS,
    MAX_SPRITE_CATALOG_BYTES,
    MAX_SPRITE_CATALOG_DECODED_PIXELS,
    MAX_SPRITE_CATALOG_ENTRIES,
    MAX_SPRITE_SOURCE_BYTES,
    MAX_SPRITE_SOURCE_DECODED_PIXELS,
    MAX_SPRITE_SOURCE_DIMENSION,
)
from .errors import Diagnostic, ValidationError

if TYPE_CHECKING:
    from .sprites import RasterTile

MAX_ATLAS_POLICY_PAGES = MAX_ATLAS_PAGES
MAX_ATLAS_POLICY_BYTES = MAX_ATLAS_AGGREGATE_BYTES


@dataclass(frozen=True, slots=True)
class AtlasPolicy:
    """Hard memory and cardinality ceilings for Python and browser caches.

    Ceilings apply per distinct policy cache, shared by sessions using that
    policy. Distinct policies retain separate caches; their residency adds up.
    There is no aggregate process-wide ceiling across policy caches.
    """

    max_pages: int = 128
    max_bytes: int = 32 * 1024 * 1024
    max_tile_pixels: int = 512 * 512 * 4
    max_page_bytes: int = 2 * 1024 * 1024
    max_source_bytes: int = 4 * 1024 * 1024
    max_source_dimension: int = 4096
    max_source_decoded_pixels: int = 4 * 1024 * 1024
    max_catalog_entries: int = 512
    max_catalog_bytes: int = 32 * 1024 * 1024
    max_catalog_decoded_pixels: int = 64 * 1024 * 1024
    max_prepared_tile_pixels: int = 512 * 512
    page_width: int = 512
    page_height: int = 512
    padding: int = 1

    def __post_init__(self) -> None:
        values = (
            self.max_pages,
            self.max_bytes,
            self.max_tile_pixels,
            self.max_page_bytes,
            self.max_source_bytes,
            self.max_source_dimension,
            self.max_source_decoded_pixels,
            self.max_catalog_entries,
            self.max_catalog_bytes,
            self.max_catalog_decoded_pixels,
            self.max_prepared_tile_pixels,
            self.page_width,
            self.page_height,
        )
        if any(isinstance(value, bool) or value <= 0 for value in values):
            raise ValueError("Atlas cache and raster limits must be positive integers")
        if self.max_pages > MAX_ATLAS_POLICY_PAGES:
            raise ValueError("max_pages exceeds the reviewed hard ceiling")
        if self.max_bytes > MAX_ATLAS_POLICY_BYTES:
            raise ValueError("max_bytes exceeds the reviewed hard ceiling")
        if self.max_tile_pixels > MAX_ATLAS_DECODED_PIXELS * 4:
            raise ValueError("max_tile_pixels exceeds the reviewed hard ceiling")
        if self.max_page_bytes > MAX_ATLAS_PAGE_BYTES:
            raise ValueError("max_page_bytes exceeds the reviewed hard ceiling")
        if isinstance(self.padding, bool) or self.padding < 1 or self.padding > 16:
            raise ValueError("padding must be an integer between 1 and 16")
        if self.max_source_bytes > MAX_SPRITE_SOURCE_BYTES:
            raise ValueError("max_source_bytes exceeds the reviewed hard ceiling")
        if self.max_source_dimension > MAX_SPRITE_SOURCE_DIMENSION:
            raise ValueError("max_source_dimension exceeds the reviewed hard ceiling")
        if self.max_source_decoded_pixels > MAX_SPRITE_SOURCE_DECODED_PIXELS:
            raise ValueError("max_source_decoded_pixels exceeds the reviewed ceiling")
        if self.max_catalog_entries > MAX_SPRITE_CATALOG_ENTRIES:
            raise ValueError("max_catalog_entries exceeds the reviewed hard ceiling")
        if self.max_catalog_bytes > MAX_SPRITE_CATALOG_BYTES:
            raise ValueError("max_catalog_bytes exceeds the reviewed hard ceiling")
        if self.max_catalog_decoded_pixels > MAX_SPRITE_CATALOG_DECODED_PIXELS:
            raise ValueError("max_catalog_decoded_pixels exceeds the reviewed ceiling")
        if self.max_prepared_tile_pixels > MAX_PREPARED_TILE_DECODED_PIXELS:
            raise ValueError("max_prepared_tile_pixels exceeds the reviewed ceiling")
        if (
            self.page_width > MAX_SPRITE_SOURCE_DIMENSION
            or self.page_height > MAX_SPRITE_SOURCE_DIMENSION
            or self.page_width * self.page_height > MAX_ATLAS_DECODED_PIXELS
        ):
            raise ValueError("atlas page dimensions exceed the reviewed hard ceiling")


@dataclass(frozen=True, slots=True)
class AtlasPage:
    page_id: str
    media_type: str
    content: bytes
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class SpriteLocation:
    page_id: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class AtlasBatchLookup:
    locations: dict[str, SpriteLocation]
    added_pages: tuple[AtlasPage, ...]
    referenced_pages: tuple[AtlasPage, ...]
    evicted_page_ids: tuple[str, ...]


@dataclass(slots=True)
class _PackedPageEntry:
    page: AtlasPage
    tile_keys: tuple[str, ...]


def resolution_bucket(value: float) -> float:
    """Round display scale up to a supported, bounded raster bucket."""

    if value <= 1:
        return 1.0
    if value <= 1.5:
        return 1.5
    return 2.0


PILLOW_SUPPORTED = SpecifierSet(">=12.3.0,<13")
ATLAS_RASTERIZER_REVISION = 1


def pillow_rasterizer_version(*, subject: str = "ATLAS") -> str:
    """Return the versioned Pillow cache identity after enforcing support."""

    try:
        import PIL
    except ImportError as error:
        raise _diagnostic(
            "SGC_ATLAS_DEPENDENCY",
            "ATLAS requires Pillow, but it is not installed.",
            "Install streamlit-graph-canvas[atlas].",
            subject,
        ) from error
    raw_version = str(PIL.__version__)
    try:
        version = Version(raw_version)
    except InvalidVersion:
        version = None
    if version is None or version not in PILLOW_SUPPORTED:
        raise _diagnostic(
            "SGC_ATLAS_DEPENDENCY_VERSION",
            f"ATLAS requires Pillow {PILLOW_SUPPORTED}; found {raw_version}.",
            "Install a supported streamlit-graph-canvas[atlas] dependency set.",
            subject,
        )
    return f"sgc-atlas-v{ATLAS_RASTERIZER_REVISION}:pillow:{version}"


def atlas_content_key(payload: object, *, subject: str = "ATLAS") -> str:
    """Hash content with the mandatory rasterizer identity and revision."""

    encoded = json.dumps(
        {
            "payload": payload,
            "rasterizer": pillow_rasterizer_version(subject=subject),
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


_ATLAS_SUBJECT = "ATLAS"


def _page_identity(content_hash: str, tile_keys: Mapping[str, object]) -> str:
    """Return a stable content address for a packed page and its tile mapping.

    Page identity is a pure function of bytes and layout, so the same tile set
    reproduces the same identifier in any process. A browser that already holds a
    page keeps it across server restarts, and the identifier is durable enough to
    serve as a cache key for content-addressed HTTP delivery later.
    """

    payload = f"packed-page:{content_hash}:{','.join(sorted(tile_keys))}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _diagnostic(code: str, message: str, action: str, subject: str) -> ValidationError:
    return ValidationError(Diagnostic(code, message, action, subject))


def _color(value: str, subject: str) -> tuple[int, int, int, int]:
    if value.startswith("var("):
        raise _diagnostic(
            "SGC_ATLAS_THEME_COLOR",
            f"ATLAS cannot resolve browser-only theme variable {value!r}.",
            "Provide literal light and dark colors for every ATLAS tone.",
            subject,
        )
    try:
        from PIL import ImageColor

        return cast(tuple[int, int, int, int], ImageColor.getcolor(value, "RGBA"))
    except (ImportError, ValueError) as error:
        raise _diagnostic(
            "SGC_ATLAS_COLOR",
            f"ATLAS cannot rasterize CSS color {value!r}: {error}.",
            "Use a Pillow-compatible literal CSS color or switch to PRIMS.",
            subject,
        ) from error


def rasterize_primitives(
    primitives: tuple[dict[str, Any], ...],
    *,
    width: float,
    height: float,
    palette: dict[str, str],
    bucket: float,
    policy: AtlasPolicy,
    subject: str,
) -> AtlasPage:
    """Rasterize the closed beta primitive vocabulary to deterministic PNG."""

    pixel_width = max(1, round(width * bucket))
    pixel_height = max(1, round(height * bucket))
    if pixel_width * pixel_height * 4 > policy.max_tile_pixels:
        raise _diagnostic(
            "SGC_ATLAS_TILE_PIXELS",
            "ATLAS tile exceeds the configured decoded-pixel limit.",
            "Reduce the badge region, display bucket, or increase the reviewed limit.",
            subject,
        )
    pillow_rasterizer_version(subject=subject)
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = bucket
    for primitive in primitives:
        fill = _color(palette[primitive["fill"]], subject)
        if primitive["kind"] == "rect":
            box = tuple(
                round(value * scale)
                for value in (
                    primitive["x"],
                    primitive["y"],
                    primitive["x"] + primitive["width"],
                    primitive["y"] + primitive["height"],
                )
            )
            draw.rounded_rectangle(
                box, radius=round(primitive["radius"] * scale), fill=fill
            )
        elif primitive["kind"] == "circle":
            cx = primitive["cx"] * scale
            cy = primitive["cy"] * scale
            radius = primitive["radius"] * scale
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius), fill=fill
            )
        else:
            font = ImageFont.load_default(size=max(1, round(primitive["size"] * scale)))
            anchor = {"start": "lm", "middle": "mm", "end": "rm"}[primitive["anchor"]]
            draw.text(
                (primitive["x"] * scale, primitive["y"] * scale),
                primitive["text"],
                fill=fill,
                font=font,
                anchor=anchor,
            )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    content = output.getvalue()
    if len(content) > policy.max_page_bytes:
        raise _diagnostic(
            "SGC_ATLAS_PAGE_BYTES",
            "ATLAS page exceeds the configured encoded-byte limit.",
            "Reduce badge complexity or increase the reviewed page limit.",
            subject,
        )
    page_id = hashlib.sha256(content).hexdigest()
    return AtlasPage(page_id, "image/png", content, pixel_width, pixel_height)


def rasterize_primitives_tile(
    primitives: tuple[dict[str, Any], ...],
    *,
    content_key: str,
    width: float,
    height: float,
    palette: dict[str, str],
    bucket: float,
    policy: AtlasPolicy,
    subject: str,
) -> RasterTile:
    """Rasterize PRIMS into the shared pre-packing tile representation."""

    from .sprites import RasterTile

    page = rasterize_primitives(
        primitives,
        width=width,
        height=height,
        palette=palette,
        bucket=bucket,
        policy=policy,
        subject=subject,
    )
    return RasterTile(content_key, page.content, page.width, page.height)


def _encode_page(
    placements: list[tuple[RasterTile, int, int]],
    *,
    policy: AtlasPolicy,
    subject: str,
) -> AtlasPage:
    from PIL import Image

    canvas = Image.new("RGBA", (policy.page_width, policy.page_height), (0, 0, 0, 0))
    for tile, x, y in placements:
        with Image.open(io.BytesIO(tile.content)) as opened:
            rgba = opened.convert("RGBA")
        if rgba.size != (tile.width, tile.height):
            raise _diagnostic(
                "SGC_ATLAS_TILE_DIMENSIONS",
                "Prepared tile bytes do not match their declared dimensions.",
                "Correct the trusted tile preparation implementation.",
                subject,
            )
        canvas.alpha_composite(rgba, (x, y))
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    content = output.getvalue()
    if len(content) > policy.max_page_bytes:
        raise _diagnostic(
            "SGC_ATLAS_PAGE_BYTES",
            "Packed atlas page exceeds the configured encoded-byte limit.",
            "Reduce page dimensions or increase the reviewed page-byte limit.",
            subject,
        )
    return AtlasPage(
        hashlib.sha256(content).hexdigest(),
        "image/png",
        content,
        policy.page_width,
        policy.page_height,
    )


def pack_tiles(
    tiles: tuple[RasterTile, ...], *, policy: AtlasPolicy, subject: str
) -> tuple[tuple[AtlasPage, dict[str, SpriteLocation]], ...]:
    """Deterministically shelf-pack one immutable batch into bounded pages."""

    unique = {tile.content_key: tile for tile in tiles}
    ordered = sorted(
        unique.values(),
        key=lambda tile: (-tile.height, -tile.width, tile.content_key),
    )
    pages: list[tuple[AtlasPage, dict[str, SpriteLocation]]] = []
    pending: list[tuple[RasterTile, int, int]] = []
    locations: dict[str, SpriteLocation] = {}
    cursor_x = policy.padding
    cursor_y = policy.padding
    row_height = 0

    def finish_page() -> None:
        nonlocal pending, locations, cursor_x, cursor_y, row_height
        if not pending:
            return
        page = _encode_page(pending, policy=policy, subject=subject)
        page_locations = {
            key: SpriteLocation(
                page.page_id,
                location.x,
                location.y,
                location.width,
                location.height,
            )
            for key, location in locations.items()
        }
        pages.append((page, page_locations))
        pending = []
        locations = {}
        cursor_x = policy.padding
        cursor_y = policy.padding
        row_height = 0

    for tile in ordered:
        if (
            tile.width + 2 * policy.padding > policy.page_width
            or tile.height + 2 * policy.padding > policy.page_height
        ):
            raise _diagnostic(
                "SGC_ATLAS_TILE_FIT",
                "Prepared tile cannot fit within an empty atlas page.",
                "Reduce the binding region or increase reviewed page dimensions.",
                subject,
            )
        if cursor_x + tile.width + policy.padding > policy.page_width:
            cursor_x = policy.padding
            cursor_y += row_height + policy.padding
            row_height = 0
        if cursor_y + tile.height + policy.padding > policy.page_height:
            finish_page()
        x, y = cursor_x, cursor_y
        pending.append((tile, x, y))
        locations[tile.content_key] = SpriteLocation("", x, y, tile.width, tile.height)
        cursor_x += tile.width + policy.padding
        row_height = max(row_height, tile.height)
    finish_page()
    return tuple(pages)


class AtlasPageCache:
    """Thread-safe, content-addressed LRU shared by every session in a process."""

    def __init__(self, policy: AtlasPolicy) -> None:
        self.policy = policy
        self._pages: OrderedDict[str, _PackedPageEntry] = OrderedDict()
        self._tile_locations: dict[str, SpriteLocation] = {}
        self._bytes = 0
        self._lock = threading.RLock()

    def resolve_tiles(self, *, tiles: Mapping[str, RasterTile]) -> AtlasBatchLookup:
        """Resolve a complete active tile set into immutable packed pages atomically."""

        if not tiles:
            return AtlasBatchLookup({}, (), (), ())
        with self._lock:
            locations: dict[str, SpriteLocation] = {}
            missing: list[RasterTile] = []
            protected: set[str] = set()
            for content_key, tile in tiles.items():
                location = self._tile_locations.get(content_key)
                if location is None or location.page_id not in self._pages:
                    missing.append(tile)
                    continue
                locations[content_key] = location
                protected.add(location.page_id)
                self._pages.move_to_end(location.page_id)
            telemetry.record_tile_lookups(hits=len(locations), misses=len(missing))

            with telemetry.measure("pack_duration"):
                raw_batches = pack_tiles(
                    tuple(missing),
                    policy=self.policy,
                    subject=_ATLAS_SUBJECT,
                )
            additions: list[_PackedPageEntry] = []
            addition_locations: dict[str, SpriteLocation] = {}
            for raw_page, raw_locations in raw_batches:
                # The packed PNG bytes already hash into raw_page.page_id. Binding
                # the tile mapping as well keeps two pages distinct when identical
                # pixels carry different crop rectangles.
                page_id = _page_identity(raw_page.page_id, raw_locations)
                page = AtlasPage(
                    page_id,
                    raw_page.media_type,
                    raw_page.content,
                    raw_page.width,
                    raw_page.height,
                )
                page_locations = {
                    key: SpriteLocation(
                        page_id,
                        location.x,
                        location.y,
                        location.width,
                        location.height,
                    )
                    for key, location in raw_locations.items()
                }
                additions.append(_PackedPageEntry(page, tuple(page_locations)))
                addition_locations.update(page_locations)
                protected.add(page_id)

            projected_pages = len(self._pages) + len(additions)
            projected_bytes = self._bytes + sum(
                len(entry.page.content) for entry in additions
            )
            # self._pages is in least-recently-used order, so the candidate list
            # is already the eviction order.
            victims: list[str] = []
            candidates = [
                page_id for page_id in self._pages if page_id not in protected
            ]
            while (
                projected_pages > self.policy.max_pages
                or projected_bytes > self.policy.max_bytes
            ):
                if not candidates:
                    telemetry.record_failure("SGC_ATLAS_WORKING_SET_LIMIT")
                    raise _diagnostic(
                        "SGC_ATLAS_WORKING_SET_LIMIT",
                        "The active sprite working set cannot fit within the "
                        "configured atlas cache limits.",
                        "Reduce sprite cardinality or increase reviewed page limits.",
                        _ATLAS_SUBJECT,
                    )
                victim_key = candidates.pop(0)
                victims.append(victim_key)
                projected_pages -= 1
                projected_bytes -= len(self._pages[victim_key].page.content)

            evicted: list[str] = []
            released_bytes = 0
            for victim_key in victims:
                victim = self._pages.pop(victim_key)
                self._bytes -= len(victim.page.content)
                released_bytes += len(victim.page.content)
                evicted.append(victim.page.page_id)
                for tile_key in victim.tile_keys:
                    self._tile_locations.pop(tile_key, None)
            added_bytes = 0
            for entry in additions:
                self._pages[entry.page.page_id] = entry
                self._bytes += len(entry.page.content)
                added_bytes += len(entry.page.content)
            telemetry.record_eviction(len(victims), released_bytes)
            telemetry.record_residency(
                pages_delta=len(additions) - len(victims),
                bytes_delta=added_bytes - released_bytes,
            )
            for content_key, location in addition_locations.items():
                self._tile_locations[content_key] = location
            locations.update(addition_locations)
            if set(locations) != set(tiles):
                raise RuntimeError("atlas tile resolution lost an active mapping")
            referenced_page_ids = {item.page_id for item in locations.values()}
            referenced_pages = tuple(
                entry.page
                for page_id, entry in self._pages.items()
                if page_id in referenced_page_ids
            )
            if {page.page_id for page in referenced_pages} != referenced_page_ids:
                raise RuntimeError("atlas page resolution lost an active page")
            return AtlasBatchLookup(
                locations,
                tuple(entry.page for entry in additions),
                referenced_pages,
                tuple(evicted),
            )

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"pages": len(self._pages), "bytes": self._bytes}


# Compatibility alias retained throughout the 0.1 release-candidate series.
AtlasCache = AtlasPageCache


class _AtlasCacheRegistry:
    """One process-global cache per distinct policy.

    Page packing depends on ``page_width``, ``page_height`` and ``padding``, so two
    policies packing the same tiles produce different pages. Keeping a cache per
    policy stops one content key from mapping to two pages. Tile identity itself is
    policy-independent, so within a policy every session shares the same entries.
    """

    def __init__(self) -> None:
        self._caches: dict[AtlasPolicy, AtlasPageCache] = {}
        self._lock = threading.RLock()

    def get(self, policy: AtlasPolicy) -> AtlasPageCache:
        with self._lock:
            cache = self._caches.get(policy)
            if cache is None:
                cache = AtlasPageCache(policy)
                self._caches[policy] = cache
            return cache

    def reset(self) -> None:
        """Discard every cache. Intended for tests and process teardown."""

        with self._lock:
            self._caches.clear()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            snapshots = [cache.snapshot() for cache in self._caches.values()]
        return {
            "policy_caches": len(snapshots),
            "pages": sum(item["pages"] for item in snapshots),
            "bytes": sum(item["bytes"] for item in snapshots),
        }


_ATLAS_CACHES = _AtlasCacheRegistry()


def atlas_cache(policy: AtlasPolicy) -> AtlasPageCache:
    """Return the process-global cache serving a policy, creating it on first use."""

    return _ATLAS_CACHES.get(policy)


def reset_atlas_caches() -> None:
    """Discard every process-global atlas cache."""

    _ATLAS_CACHES.reset()


def atlas_cache_snapshot() -> dict[str, int]:
    """Return aggregate residency across every process-global atlas cache."""

    return _ATLAS_CACHES.snapshot()
