from __future__ import annotations

import base64
import hashlib
import io
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import PIL
import pytest
from streamlit_graph_canvas import (
    AtlasCache,
    AtlasPolicy,
    BadgeBinding,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PaletteTone,
    Region,
    Transport,
    ValidationError,
    atlas_cache,
    atlas_cache_snapshot,
    enable_renderers,
    format_csp,
    reset_atlas_caches,
    serialize_graph,
    streamlit_host_csp,
)
from streamlit_graph_canvas.atlas import (
    ATLAS_RASTERIZER_REVISION,
    PILLOW_SUPPORTED,
    AtlasPage,
    atlas_content_key,
    pillow_rasterizer_version,
    resolution_bucket,
)
from streamlit_graph_canvas.csp import telemetry_origin
from streamlit_graph_canvas.sprites import RasterTile


def page(content: bytes = b"png") -> AtlasPage:
    return AtlasPage("a" * 64, "image/png", content, 1, 1)


def tile(key: str, *, shade: int, size: int = 8) -> RasterTile:
    """Build a solid-colour PNG tile whose bytes vary with ``shade``."""

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), (shade, shade, shade, 255)).save(
        buffer, format="PNG"
    )
    return RasterTile(key, buffer.getvalue(), size, size)


@pytest.fixture(autouse=True)
def _clean_process_caches() -> Iterator[None]:
    reset_atlas_caches()
    yield
    reset_atlas_caches()


def test_resolution_buckets_are_bounded() -> None:
    assert [resolution_bucket(value) for value in (0.5, 1, 1.1, 1.5, 3)] == [
        1,
        1,
        1.5,
        1.5,
        2,
    ]


def test_atlas_rasterizer_records_a_supported_pillow_version() -> None:
    identity = pillow_rasterizer_version()
    prefix = f"sgc-atlas-v{ATLAS_RASTERIZER_REVISION}:pillow:"
    assert identity.startswith(prefix)
    assert identity.removeprefix(prefix) in PILLOW_SUPPORTED


@pytest.mark.parametrize("version", ["12.2.0", "13.0.0", "not-a-version"])
def test_atlas_rejects_unsupported_or_invalid_pillow_versions(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    monkeypatch.setattr(PIL, "__version__", version)
    with pytest.raises(ValidationError, match="SGC_ATLAS_DEPENDENCY_VERSION"):
        pillow_rasterizer_version()


def test_atlas_accepts_supported_pillow_minor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PIL, "__version__", "12.4.0")
    assert pillow_rasterizer_version().endswith(":pillow:12.4.0")


def test_atlas_content_key_always_varies_with_rasterizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PIL, "__version__", "12.3.0")
    first = atlas_content_key({"same": "payload"})
    monkeypatch.setattr(PIL, "__version__", "12.4.0")
    second = atlas_content_key({"same": "payload"})
    assert first != second


@pytest.mark.parametrize(
    "updates",
    [
        {"max_pages": 0},
        {"max_pages": 513},
        {"max_bytes": 64 * 1024 * 1024 + 1},
        {"max_tile_pixels": 512 * 512 * 4 + 1},
        {"max_page_bytes": 2 * 1024 * 1024 + 1},
    ],
)
def test_atlas_policy_rejects_invalid_limits(updates: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        AtlasPolicy(**updates)


def test_identical_content_resolves_to_one_shared_page() -> None:
    """Two consumers of the same tile share one page rather than duplicating it."""

    cache = AtlasCache(AtlasPolicy())
    first = cache.resolve_tiles(tiles={"shared": tile("shared", shade=10)})
    second = cache.resolve_tiles(tiles={"shared": tile("shared", shade=10)})
    assert first.locations["shared"] == second.locations["shared"]
    assert second.added_pages == ()
    assert cache.snapshot()["pages"] == 1


def test_distinct_badge_content_never_collides() -> None:
    """Different rendered content keeps distinct locations on a shared sheet."""

    cache = AtlasCache(AtlasPolicy())
    resolved = cache.resolve_tiles(
        tiles={
            "severity": tile("severity", shade=20),
            "count": tile("count", shade=200),
        }
    )
    severity = resolved.locations["severity"]
    count = resolved.locations["count"]
    assert (severity.x, severity.y) != (count.x, count.y)
    # Both tiles fit one page, so a shared sheet must still crop them apart.
    assert severity.page_id == count.page_id


def test_aggregate_pressure_evicts_the_globally_least_recently_used_page() -> None:
    # A 12px page holds exactly one 8px tile once padding is applied, so each
    # tile lands on its own page and eviction order is observable.
    cache = AtlasCache(AtlasPolicy(max_pages=2, page_width=12, page_height=12))
    cache.resolve_tiles(tiles={"first": tile("first", shade=30)})
    cache.resolve_tiles(tiles={"second": tile("second", shade=60)})
    # Touching "first" makes "second" the least recently used entry.
    cache.resolve_tiles(tiles={"first": tile("first", shade=30)})
    third = cache.resolve_tiles(tiles={"third": tile("third", shade=90)})
    assert len(third.evicted_page_ids) == 1
    assert cache.snapshot()["pages"] == 2
    reresolved = cache.resolve_tiles(tiles={"first": tile("first", shade=30)})
    assert reresolved.added_pages == ()


def test_irreducible_working_set_fails_with_a_diagnostic() -> None:
    """An oversized working set raises rather than escaping as StopIteration."""

    cache = AtlasCache(AtlasPolicy(max_pages=1, page_width=12, page_height=12))
    with pytest.raises(ValidationError, match="SGC_ATLAS_WORKING_SET_LIMIT"):
        cache.resolve_tiles(
            tiles={
                "one": tile("one", shade=40),
                "two": tile("two", shade=80),
                "three": tile("three", shade=120),
            }
        )


def test_page_identity_is_stable_across_caches_and_processes() -> None:
    """Page IDs are pure content addresses, so a browser copy survives a restart."""

    tiles = {"stable": tile("stable", shade=55)}
    left = AtlasCache(AtlasPolicy()).resolve_tiles(tiles=tiles)
    right = AtlasCache(AtlasPolicy()).resolve_tiles(tiles=tiles)
    assert left.locations["stable"].page_id == right.locations["stable"].page_id
    assert left.added_pages[0].page_id == right.added_pages[0].page_id


def test_process_registry_returns_one_cache_per_policy() -> None:
    policy = AtlasPolicy()
    other = AtlasPolicy(page_width=256, page_height=256)
    assert atlas_cache(policy) is atlas_cache(policy)
    assert atlas_cache(policy) is not atlas_cache(other)
    atlas_cache(policy).resolve_tiles(tiles={"one": tile("one", shade=70)})
    snapshot = atlas_cache_snapshot()
    assert snapshot["policy_caches"] == 2
    assert snapshot["pages"] == 1
    reset_atlas_caches()
    assert atlas_cache_snapshot() == {"policy_caches": 0, "pages": 0, "bytes": 0}


def test_concurrent_resolution_preserves_cache_integrity() -> None:
    cache = atlas_cache(AtlasPolicy())

    def resolve(index: int) -> str:
        key = f"tile-{index % 4}"
        resolved = cache.resolve_tiles(tiles={key: tile(key, shade=10 + index % 4)})
        return resolved.locations[key].page_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        page_ids = set(executor.map(resolve, range(100)))
    assert page_ids
    assert cache.snapshot()["pages"] >= 1


def test_atlas_serialization_emits_content_addressed_page_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    schema = GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(
                    BadgeBinding(
                        "count",
                        "streamlit-graph-canvas/contrib/count-chip",
                        Region.at(0, 0, 42, 22),
                        transport=Transport.ATLAS,
                    ),
                ),
            )
        },
        edge_types={},
        palette={
            "accent": PaletteTone("#2563eb", "#60a5fa"),
            "on_accent": PaletteTone("#ffffff", "#0f172a"),
        },
    )
    graph = GraphData((Node("a", "item", "A", badges={"count": 7}),), ())
    cache = AtlasCache(AtlasPolicy())
    first = serialize_graph(
        schema, graph, renderer_registry=registry, atlas_cache=cache
    )
    page_delta = first.envelope["atlas"]["pages"]
    assert len(page_delta) == 1
    page_id = page_delta[0]["pageId"]
    png = base64.b64decode(page_delta[0]["base64"])
    assert page_delta[0]["contentSha256"] == hashlib.sha256(png).hexdigest()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    repeated = serialize_graph(
        schema,
        graph,
        renderer_registry=registry,
        atlas_cache=AtlasCache(AtlasPolicy()),
    )
    assert repeated.envelope["atlas"]["pages"] == page_delta
    badge = first.envelope["presentation"]["nodes"][0]["badges"][0]
    assert badge["atlas"]["pageId"] == page_id
    second = serialize_graph(
        schema,
        graph,
        renderer_registry=registry,
        atlas_cache=cache,
        atlas_known_pages=frozenset({page_id}),
    )
    assert second.envelope["atlas"]["pages"] == []

    original_version = PIL.__version__
    alternate_version = "12.4.0" if original_version != "12.4.0" else "12.3.0"
    monkeypatch.setattr(PIL, "__version__", alternate_version)
    changed_rasterizer = serialize_graph(
        schema,
        graph,
        renderer_registry=registry,
        atlas_cache=cache,
        atlas_known_pages=frozenset({page_id}),
    )
    changed_pages = changed_rasterizer.envelope["atlas"]["pages"]
    assert len(changed_pages) == 1
    assert changed_pages[0]["pageId"] != page_id
    assert cache.snapshot()["pages"] == 2


def test_atlas_tenant_is_rejected_rather_than_silently_ignored() -> None:
    """A removed security-shaped parameter must fail loudly, not be dropped."""

    from streamlit_graph_canvas import graph_canvas

    schema = GraphSchema(node_types={"item": NodeType("item")}, edge_types={})
    graph = GraphData((Node("a", "item", "A"),), ())
    with pytest.raises(ValidationError, match="SGC_ATLAS_TENANT_REMOVED"):
        graph_canvas(graph, schema, key="k", atlas_tenant="org:acme")


def test_transport_csp_never_requires_executable_blob_or_eval() -> None:
    policy = format_csp((Transport.JAVASCRIPT, Transport.ATLAS))
    assert "script-src 'self'" in policy
    assert "img-src 'self' data: blob:" in policy
    assert "unsafe-eval" not in policy
    assert "script-src 'self' blob:" not in policy
    host_policy = streamlit_host_csp((Transport.JAVASCRIPT, Transport.ATLAS))
    assert "'wasm-unsafe-eval'" in host_policy
    assert "base-uri 'none'" in host_policy
    assert "font-src 'self' data:" in host_policy


def test_origin_specific_csp_uses_only_the_exact_websocket_origin() -> None:
    policy = streamlit_host_csp(
        (Transport.JAVASCRIPT, Transport.ATLAS),
        app_origin="https://canvas.example:8443",
    )
    connect = next(
        directive
        for directive in policy.split("; ")
        if directive.startswith("connect-src")
    )
    assert connect == "connect-src 'self' wss://canvas.example:8443"


def test_csp_accepts_exact_frame_ancestors() -> None:
    policy = streamlit_host_csp(
        (Transport.PRIMS,),
        app_origin="https://canvas.example:8443",
        frame_ancestors=("'self'", "https://portal.example"),
    )
    assert "frame-ancestors 'self' https://portal.example" in policy


@pytest.mark.parametrize(
    "ancestor",
    (
        "https://*.example.com",
        "https://user@example.com",
        "https://example.com/path",
        "data:",
    ),
)
def test_csp_rejects_non_exact_frame_ancestors(ancestor: str) -> None:
    with pytest.raises(ValueError, match="frame_ancestors"):
        streamlit_host_csp(frame_ancestors=(ancestor,))


def test_csp_rejects_combined_none_frame_ancestor() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        streamlit_host_csp(frame_ancestors=("'none'", "'self'"))


def test_telemetry_endpoint_adds_only_its_origin_to_connect_src() -> None:
    policy = streamlit_host_csp(
        app_origin="https://canvas.example:8443",
        telemetry_endpoint="https://otel.example:4318/v1/metrics",
    )
    connect = next(
        directive
        for directive in policy.split("; ")
        if directive.startswith("connect-src")
    )
    # The path is dropped: CSP sources are origins, not URLs.
    assert connect == (
        "connect-src 'self' wss://canvas.example:8443 https://otel.example:4318"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://*.example.com/v1/metrics",
        "https://user:pass@example.com/v1/metrics",
        "ftp://example.com/v1/metrics",
        "https://example.com/v1/metrics?token=secret",
        "https://example.com/v1/metrics#fragment",
    ],
)
def test_telemetry_endpoint_rejects_unusable_urls(endpoint: str) -> None:
    with pytest.raises(ValueError, match="telemetry endpoint"):
        telemetry_origin(endpoint)


@pytest.mark.parametrize(
    "origin",
    [
        "https://*.example.com",
        "https://user@example.com",
        "https://example.com/path",
        "javascript:alert(1)",
    ],
)
def test_origin_specific_csp_rejects_non_origins(origin: str) -> None:
    with pytest.raises(ValueError, match="exact HTTP"):
        streamlit_host_csp(app_origin=origin)
