"""Bounded, tenant-isolated raster atlas cache for PRIMS renderers."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import secrets
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

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


class AtlasScope(StrEnum):
    """Lifetime and isolation boundary for raster pages."""

    SESSION = "session"
    TENANT = "tenant"


@dataclass(frozen=True, slots=True)
class AtlasPolicy:
    """Hard memory and cardinality ceilings for Python and browser caches."""

    scope: AtlasScope = AtlasScope.SESSION
    max_pages: int = 128
    max_bytes: int = 32 * 1024 * 1024
    max_tenant_pages: int = 64
    max_tenant_bytes: int = 16 * 1024 * 1024
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
            self.max_tenant_pages,
            self.max_tenant_bytes,
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
        if self.max_tenant_pages > self.max_pages:
            raise ValueError("max_tenant_pages cannot exceed max_pages")
        if self.max_tenant_bytes > self.max_bytes:
            raise ValueError("max_tenant_bytes cannot exceed max_bytes")
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
class AtlasLookup:
    page: AtlasPage
    evicted_page_ids: tuple[str, ...]
    cache_hit: bool


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
class _CacheEntry:
    tenant: str
    content_key: str
    page: AtlasPage


@dataclass(slots=True)
class _PackedPageEntry:
    tenant: str
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
    """Thread-safe LRU with aggregate and per-tenant limits."""

    def __init__(
        self, policy: AtlasPolicy, *, identity_key: bytes | None = None
    ) -> None:
        self.policy = policy
        self._identity_key = identity_key or _PROCESS_IDENTITY_KEY
        self._entries: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()
        self._packed_entries: OrderedDict[tuple[str, str], _PackedPageEntry] = (
            OrderedDict()
        )
        self._tile_locations: dict[tuple[str, str], SpriteLocation] = {}
        self._bytes = 0
        self._lock = threading.RLock()

    def resolve_tiles(
        self, *, tenant: str, tiles: Mapping[str, RasterTile]
    ) -> AtlasBatchLookup:
        """Resolve a complete active tile set into immutable packed pages atomically."""

        if not tiles:
            return AtlasBatchLookup({}, (), (), ())
        with self._lock:
            locations: dict[str, SpriteLocation] = {}
            missing: list[RasterTile] = []
            protected: set[str] = set()
            for content_key, tile in tiles.items():
                location = self._tile_locations.get((tenant, content_key))
                if (
                    location is None
                    or (tenant, location.page_id) not in self._packed_entries
                ):
                    missing.append(tile)
                    continue
                locations[content_key] = location
                protected.add(location.page_id)
                self._packed_entries.move_to_end((tenant, location.page_id))

            raw_batches = pack_tiles(
                tuple(missing),
                policy=self.policy,
                subject=tenant_subject(tenant, identity_key=self._identity_key),
            )
            additions: list[_PackedPageEntry] = []
            addition_locations: dict[str, SpriteLocation] = {}
            for raw_page, raw_locations in raw_batches:
                page_id = _identity(
                    self._identity_key,
                    "packed-page:"
                    f"{tenant}:{raw_page.page_id}:{','.join(sorted(raw_locations))}",
                )
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
                additions.append(_PackedPageEntry(tenant, page, tuple(page_locations)))
                addition_locations.update(page_locations)
                protected.add(page_id)

            projected_pages = (
                len(self._entries) + len(self._packed_entries) + len(additions)
            )
            projected_bytes = self._bytes + sum(
                len(entry.page.content) for entry in additions
            )
            tenant_legacy = [
                entry for entry in self._entries.values() if entry.tenant == tenant
            ]
            tenant_packed = [
                entry
                for entry in self._packed_entries.values()
                if entry.tenant == tenant
            ]
            tenant_pages = len(tenant_legacy) + len(tenant_packed) + len(additions)
            tenant_bytes = (
                sum(len(entry.page.content) for entry in tenant_legacy)
                + sum(len(entry.page.content) for entry in tenant_packed)
                + sum(len(entry.page.content) for entry in additions)
            )
            victims: list[tuple[str, str]] = []
            candidates = [
                key
                for key, entry in self._packed_entries.items()
                if entry.tenant == tenant and entry.page.page_id not in protected
            ]
            while (
                projected_pages > self.policy.max_pages
                or projected_bytes > self.policy.max_bytes
                or tenant_pages > self.policy.max_tenant_pages
                or tenant_bytes > self.policy.max_tenant_bytes
            ):
                if not candidates:
                    raise _diagnostic(
                        "SGC_ATLAS_WORKING_SET_LIMIT",
                        "The active sprite working set cannot fit within the "
                        "configured atlas cache limits.",
                        "Reduce sprite cardinality or increase reviewed page limits.",
                        tenant_subject(tenant, identity_key=self._identity_key),
                    )
                victim_key = candidates.pop(0)
                victim = self._packed_entries[victim_key]
                victims.append(victim_key)
                size = len(victim.page.content)
                projected_pages -= 1
                projected_bytes -= size
                tenant_pages -= 1
                tenant_bytes -= size

            evicted: list[str] = []
            for victim_key in victims:
                victim = self._packed_entries.pop(victim_key)
                self._bytes -= len(victim.page.content)
                evicted.append(victim.page.page_id)
                for tile_key in victim.tile_keys:
                    self._tile_locations.pop((tenant, tile_key), None)
            for entry in additions:
                self._packed_entries[(tenant, entry.page.page_id)] = entry
                self._bytes += len(entry.page.content)
            for content_key, location in addition_locations.items():
                self._tile_locations[(tenant, content_key)] = location
            locations.update(addition_locations)
            if set(locations) != set(tiles):
                raise RuntimeError("atlas tile resolution lost an active mapping")
            referenced_page_ids = {item.page_id for item in locations.values()}
            referenced_pages = tuple(
                entry.page
                for (_tenant, page_id), entry in self._packed_entries.items()
                if entry.tenant == tenant and page_id in referenced_page_ids
            )
            if {page.page_id for page in referenced_pages} != referenced_page_ids:
                raise RuntimeError("atlas page resolution lost an active page")
            return AtlasBatchLookup(
                locations,
                tuple(entry.page for entry in additions),
                referenced_pages,
                tuple(evicted),
            )

    def get_or_create(
        self,
        *,
        tenant: str,
        content_key: str,
        create: Callable[[], AtlasPage],
    ) -> AtlasLookup:
        cache_key = (tenant, content_key)
        with self._lock:
            if entry := self._entries.get(cache_key):
                self._entries.move_to_end(cache_key)
                return AtlasLookup(entry.page, (), True)
            raw_page = create()
            page = AtlasPage(
                _identity(
                    self._identity_key,
                    f"page:{tenant}:{content_key}:{raw_page.page_id}",
                ),
                raw_page.media_type,
                raw_page.content,
                raw_page.width,
                raw_page.height,
            )
            entry = _CacheEntry(tenant, content_key, page)
            self._entries[cache_key] = entry
            self._bytes += len(page.content)
            evicted: list[str] = []
            while self._over_limit(tenant):
                victim_key = self._oldest_key(tenant)
                victim = self._entries.pop(victim_key)
                self._bytes -= len(victim.page.content)
                evicted.append(victim.page.page_id)
            if cache_key not in self._entries:
                raise _diagnostic(
                    "SGC_ATLAS_CACHE_LIMIT",
                    "A single ATLAS page cannot fit within the configured "
                    "cache limits.",
                    "Increase the per-tenant limits or reduce the badge raster size.",
                    tenant_subject(tenant, identity_key=self._identity_key),
                )
            return AtlasLookup(page, tuple(evicted), False)

    def _tenant_usage(self, tenant: str) -> tuple[int, int]:
        legacy = [entry for entry in self._entries.values() if entry.tenant == tenant]
        packed = [
            entry for entry in self._packed_entries.values() if entry.tenant == tenant
        ]
        return len(legacy) + len(packed), sum(
            len(entry.page.content) for entry in legacy
        ) + sum(len(entry.page.content) for entry in packed)

    def _over_limit(self, tenant: str) -> bool:
        tenant_pages, tenant_bytes = self._tenant_usage(tenant)
        return (
            len(self._entries) + len(self._packed_entries) > self.policy.max_pages
            or self._bytes > self.policy.max_bytes
            or tenant_pages > self.policy.max_tenant_pages
            or tenant_bytes > self.policy.max_tenant_bytes
        )

    def _oldest_key(self, tenant: str) -> tuple[str, str]:
        return next(key for key in self._entries if key[0] == tenant)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "pages": len(self._entries) + len(self._packed_entries),
                "bytes": self._bytes,
            }


# Compatibility alias retained throughout the 0.1 release-candidate series.
AtlasCache = AtlasPageCache


_PROCESS_IDENTITY_KEY = secrets.token_bytes(32)


def _identity(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def tenant_subject(tenant: str, *, identity_key: bytes | None = None) -> str:
    """Return a process-scoped tenant pseudonym safe for diagnostics."""

    pseudonym = _identity(identity_key or _PROCESS_IDENTITY_KEY, f"tenant:{tenant}")
    return f"tenant:{pseudonym[:12]}"


@dataclass(slots=True)
class _ManagedCache:
    cache: AtlasCache
    leases: int = 0


class AtlasCacheLease:
    """Explicit active-use lease for a bounded process tenant cache."""

    def __init__(self, manager: TenantAtlasManager, policy: AtlasPolicy) -> None:
        self._manager = manager
        self._policy = policy
        self._closed = False
        self.cache = manager._acquire(policy)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._manager._release(self._policy)

    def __enter__(self) -> AtlasCache:
        return self.cache

    def __exit__(self, *_: object) -> None:
        self.close()


class TenantAtlasManager:
    """Bounded registry that never displaces an actively leased policy cache."""

    def __init__(
        self, *, max_policy_caches: int = 4, identity_key: bytes | None = None
    ) -> None:
        if isinstance(max_policy_caches, bool) or max_policy_caches <= 0:
            raise ValueError("max_policy_caches must be a positive integer")
        self.max_policy_caches = max_policy_caches
        self.max_total_pages = max_policy_caches * MAX_ATLAS_POLICY_PAGES
        self.max_total_bytes = max_policy_caches * MAX_ATLAS_POLICY_BYTES
        self._identity_key = identity_key or _PROCESS_IDENTITY_KEY
        self._caches: OrderedDict[AtlasPolicy, _ManagedCache] = OrderedDict()
        self._lock = threading.RLock()

    def acquire(self, policy: AtlasPolicy) -> AtlasCacheLease:
        if policy.scope is not AtlasScope.TENANT:
            raise ValueError("A process tenant cache requires AtlasScope.TENANT")
        return AtlasCacheLease(self, policy)

    def _acquire(self, policy: AtlasPolicy) -> AtlasCache:
        with self._lock:
            managed = self._caches.get(policy)
            if managed is None:
                if len(self._caches) >= self.max_policy_caches:
                    idle = next(
                        (
                            candidate
                            for candidate, item in self._caches.items()
                            if item.leases == 0
                        ),
                        None,
                    )
                    if idle is None:
                        raise _diagnostic(
                            "SGC_ATLAS_MANAGER_LIMIT",
                            "All process ATLAS policy cache slots are active.",
                            "Reuse an existing reviewed policy or retry after its "
                            "active render completes.",
                            "ATLAS manager",
                        )
                    del self._caches[idle]
                managed = _ManagedCache(
                    AtlasCache(policy, identity_key=self._identity_key)
                )
                self._caches[policy] = managed
            managed.leases += 1
            self._caches.move_to_end(policy)
            return managed.cache

    def _release(self, policy: AtlasPolicy) -> None:
        with self._lock:
            managed = self._caches.get(policy)
            if managed is None or managed.leases <= 0:
                raise RuntimeError("ATLAS cache lease accounting is inconsistent")
            managed.leases -= 1

    def reset(self) -> None:
        with self._lock:
            if any(managed.leases for managed in self._caches.values()):
                raise RuntimeError("cannot reset ATLAS manager with active leases")
            self._caches.clear()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "policy_caches": len(self._caches),
                "active_leases": sum(item.leases for item in self._caches.values()),
                "pages": sum(
                    item.cache.snapshot()["pages"] for item in self._caches.values()
                ),
                "bytes": sum(
                    item.cache.snapshot()["bytes"] for item in self._caches.values()
                ),
            }


_TENANT_ATLAS_MANAGER = TenantAtlasManager()


def tenant_atlas_cache(policy: AtlasPolicy) -> AtlasCacheLease:
    """Lease a bounded process cache whose entries remain tenant-isolated."""

    return _TENANT_ATLAS_MANAGER.acquire(policy)
