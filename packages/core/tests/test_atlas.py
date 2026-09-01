from __future__ import annotations

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor

import PIL
import pytest
from streamlit_graph_canvas import (
    AtlasCache,
    AtlasPolicy,
    AtlasScope,
    BadgeBinding,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PaletteTone,
    Region,
    Transport,
    ValidationError,
    enable_renderers,
    format_csp,
    serialize_graph,
    streamlit_host_csp,
)
from streamlit_graph_canvas.atlas import (
    ATLAS_RASTERIZER_REVISION,
    PILLOW_SUPPORTED,
    AtlasPage,
    TenantAtlasManager,
    atlas_content_key,
    pillow_rasterizer_version,
    resolution_bucket,
    tenant_subject,
)


def page(content: bytes = b"png") -> AtlasPage:
    return AtlasPage("a" * 64, "image/png", content, 1, 1)


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
        {"max_pages": 2, "max_tenant_pages": 3},
        {"max_bytes": 2, "max_tenant_bytes": 3},
        {"max_pages": 513},
        {"max_bytes": 64 * 1024 * 1024 + 1},
        {"max_tile_pixels": 512 * 512 * 4 + 1},
        {"max_page_bytes": 2 * 1024 * 1024 + 1},
    ],
)
def test_atlas_policy_rejects_invalid_limits(updates: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        AtlasPolicy(**updates)


def test_tenant_cache_isolates_ids_and_enforces_per_tenant_lru() -> None:
    policy = AtlasPolicy(
        scope=AtlasScope.TENANT,
        max_pages=4,
        max_bytes=100,
        max_tenant_pages=1,
        max_tenant_bytes=50,
    )
    cache = AtlasCache(policy)
    tenant_a = cache.get_or_create(tenant="a", content_key="one", create=lambda: page())
    tenant_b = cache.get_or_create(tenant="b", content_key="one", create=lambda: page())
    assert tenant_a.page.page_id != tenant_b.page.page_id
    replacement = cache.get_or_create(
        tenant="a", content_key="two", create=lambda: page(b"next")
    )
    assert tenant_a.page.page_id in replacement.evicted_page_ids
    assert cache.snapshot() == {"pages": 2, "bytes": 7}


def test_aggregate_pressure_never_evicts_another_tenant() -> None:
    policy = AtlasPolicy(
        scope=AtlasScope.TENANT,
        max_pages=2,
        max_bytes=100,
        max_tenant_pages=2,
        max_tenant_bytes=100,
    )
    cache = AtlasCache(policy, identity_key=b"f" * 32)
    victim = cache.get_or_create(
        tenant="victim", content_key="stable", create=lambda: page(b"victim")
    )
    attacker_first = cache.get_or_create(
        tenant="attacker", content_key="one", create=lambda: page(b"one")
    )
    attacker_second = cache.get_or_create(
        tenant="attacker", content_key="two", create=lambda: page(b"two")
    )
    assert attacker_second.evicted_page_ids == (attacker_first.page.page_id,)
    victim_hit = cache.get_or_create(
        tenant="victim", content_key="stable", create=lambda: page(b"changed")
    )
    assert victim_hit.cache_hit is True
    assert victim_hit.page.page_id == victim.page.page_id


def test_tenant_identities_use_injected_hmac_secrets() -> None:
    policy = AtlasPolicy(scope=AtlasScope.TENANT)
    left = AtlasCache(policy, identity_key=b"a" * 32).get_or_create(
        tenant="predictable", content_key="same", create=page
    )
    right = AtlasCache(policy, identity_key=b"b" * 32).get_or_create(
        tenant="predictable", content_key="same", create=page
    )
    assert left.page.page_id != right.page.page_id
    assert tenant_subject("predictable", identity_key=b"a" * 32) != tenant_subject(
        "predictable", identity_key=b"b" * 32
    )
    assert "predictable" not in tenant_subject("predictable", identity_key=b"a" * 32)


def test_tenant_manager_bounds_active_policy_caches_and_reclaims_idle() -> None:
    manager = TenantAtlasManager(max_policy_caches=1, identity_key=b"m" * 32)
    first_policy = AtlasPolicy(scope=AtlasScope.TENANT)
    second_policy = AtlasPolicy(scope=AtlasScope.TENANT, max_pages=64)
    first = manager.acquire(first_policy)
    with pytest.raises(ValidationError, match="SGC_ATLAS_MANAGER_LIMIT"):
        manager.acquire(second_policy)
    first.close()
    with manager.acquire(second_policy) as cache:
        assert cache.policy == second_policy
    assert manager.snapshot() == {
        "policy_caches": 1,
        "active_leases": 0,
        "pages": 0,
        "bytes": 0,
    }
    manager.reset()
    assert manager.snapshot()["policy_caches"] == 0


def test_tenant_manager_lease_accounting_is_thread_safe() -> None:
    manager = TenantAtlasManager(max_policy_caches=1)
    policy = AtlasPolicy(scope=AtlasScope.TENANT)

    def use_cache(_: int) -> int:
        with manager.acquire(policy) as cache:
            return cache.policy.max_pages

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert set(executor.map(use_cache, range(100))) == {policy.max_pages}
    assert manager.snapshot()["active_leases"] == 0


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
    assert hashlib.sha256(png).hexdigest() == (
        "f781de2ee9fab30b26ec22e20634a78f1dab5b8655399f50986cbfa210d2f54e"
    )
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
