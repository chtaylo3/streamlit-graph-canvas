"""Bounded, tenant-isolated raster atlas cache for PRIMS renderers."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import secrets
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .contract import MAX_ATLAS_DECODED_PIXELS, MAX_ATLAS_PAGE_BYTES
from .errors import Diagnostic, ValidationError

MAX_ATLAS_POLICY_PAGES = 512
MAX_ATLAS_POLICY_BYTES = 64 * 1024 * 1024


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

    def __post_init__(self) -> None:
        values = (
            self.max_pages,
            self.max_bytes,
            self.max_tenant_pages,
            self.max_tenant_bytes,
            self.max_tile_pixels,
            self.max_page_bytes,
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


@dataclass(slots=True)
class _CacheEntry:
    tenant: str
    content_key: str
    page: AtlasPage


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


class AtlasCache:
    """Thread-safe LRU with aggregate and per-tenant limits."""

    def __init__(
        self, policy: AtlasPolicy, *, identity_key: bytes | None = None
    ) -> None:
        self.policy = policy
        self._identity_key = identity_key or _PROCESS_IDENTITY_KEY
        self._entries: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

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
        entries = [entry for entry in self._entries.values() if entry.tenant == tenant]
        return len(entries), sum(len(entry.page.content) for entry in entries)

    def _over_limit(self, tenant: str) -> bool:
        tenant_pages, tenant_bytes = self._tenant_usage(tenant)
        return (
            len(self._entries) > self.policy.max_pages
            or self._bytes > self.policy.max_bytes
            or tenant_pages > self.policy.max_tenant_pages
            or tenant_bytes > self.policy.max_tenant_bytes
        )

    def _oldest_key(self, tenant: str) -> tuple[str, str]:
        return next(key for key in self._entries if key[0] == tenant)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"pages": len(self._entries), "bytes": self._bytes}


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
