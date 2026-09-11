from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider, UpDownCounter
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    InMemoryMetricReader,
)
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
    enable_renderers,
    reset_atlas_caches,
    serialize_graph,
    telemetry,
)
from streamlit_graph_canvas.sprites import RasterTile


def tile(key: str, *, shade: int, size: int = 8) -> RasterTile:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), (shade, shade, shade, 255)).save(
        buffer, format="PNG"
    )
    return RasterTile(key, buffer.getvalue(), size, size)


# OpenTelemetry permits setting the global provider only once per process, so the
# reader is installed at import time and shared. Delta temporality makes each
# collection return only what happened since the previous one, which keeps tests
# independent of each other's counts.
_MEMORY = InMemoryMetricReader(
    preferred_temporality={
        Counter: AggregationTemporality.DELTA,
        UpDownCounter: AggregationTemporality.DELTA,
        Histogram: AggregationTemporality.DELTA,
    }
)
metrics.set_meter_provider(MeterProvider(metric_readers=[_MEMORY]))


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    telemetry.reset_instruments_for_tests()
    reset_atlas_caches()
    _MEMORY.get_metrics_data()  # Discard anything an earlier test recorded.
    yield _MEMORY
    reset_atlas_caches()


def collect(memory: InMemoryMetricReader) -> dict[str, list[Any]]:
    """Drain the reader once and group data points by instrument name.

    Delta temporality means each collection consumes what it returns, so a test
    must collect exactly once and then query the result.
    """

    data = memory.get_metrics_data()
    grouped: dict[str, list[Any]] = {}
    if data is None:
        return grouped
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                grouped.setdefault(metric.name, []).extend(metric.data.data_points)
    return grouped


def total(collected: dict[str, list[Any]], name: str, **attributes: str) -> float:
    return sum(
        point.value
        for point in collected.get(name, [])
        if all(point.attributes.get(key) == value for key, value in attributes.items())
    )


def test_tile_lookups_split_hits_from_misses(reader: InMemoryMetricReader) -> None:
    cache = AtlasCache(AtlasPolicy())
    cache.resolve_tiles(tiles={"a": tile("a", shade=10), "b": tile("b", shade=20)})
    cache.resolve_tiles(tiles={"a": tile("a", shade=10), "c": tile("c", shade=30)})
    collected = collect(reader)
    assert total(collected, "sgc.atlas.tile.lookups", result="miss") == 3
    assert total(collected, "sgc.atlas.tile.lookups", result="hit") == 1


def test_eviction_and_residency_are_recorded(reader: InMemoryMetricReader) -> None:
    cache = AtlasCache(AtlasPolicy(max_pages=1, page_width=12, page_height=12))
    cache.resolve_tiles(tiles={"first": tile("first", shade=40)})
    cache.resolve_tiles(tiles={"second": tile("second", shade=80)})
    resident_bytes = cache.snapshot()["bytes"]
    collected = collect(reader)
    assert total(collected, "sgc.atlas.pages.evicted") == 1
    # One page in, one page out, so residency nets back to a single page.
    assert total(collected, "sgc.atlas.pages.resident") == 1
    assert total(collected, "sgc.atlas.bytes.resident") == resident_bytes


def test_working_set_failure_is_attributed_to_its_diagnostic_code(
    reader: InMemoryMetricReader,
) -> None:
    cache = AtlasCache(AtlasPolicy(max_pages=1, page_width=12, page_height=12))
    with pytest.raises(ValidationError, match="SGC_ATLAS_WORKING_SET_LIMIT"):
        cache.resolve_tiles(
            tiles={
                "one": tile("one", shade=40),
                "two": tile("two", shade=80),
                "three": tile("three", shade=120),
            }
        )
    collected = collect(reader)
    assert (
        total(collected, "sgc.atlas.failures", code="SGC_ATLAS_WORKING_SET_LIMIT") == 1
    )


def test_durations_are_recorded_in_seconds(reader: InMemoryMetricReader) -> None:
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
                        transport=Transport.RASTER,
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
    graph = GraphData((Node("a", "item", "A", badges={"count": 3}),), ())
    serialize_graph(schema, graph, renderer_registry=registry)

    collected = collect(reader)
    serialize_points = collected.get("sgc.serialize.duration", [])
    pack_points = collected.get("sgc.atlas.pack.duration", [])
    assert serialize_points and serialize_points[0].count == 1
    assert pack_points and pack_points[0].count == 1
    # Seconds, per the OpenTelemetry duration convention.
    assert 0 < serialize_points[0].sum < 60


def test_instruments_are_inert_without_the_otel_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rendering must work unchanged when opentelemetry-api is not installed."""

    import sys

    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    telemetry.reset_instruments_for_tests()
    try:
        assert isinstance(telemetry.instruments().failures, telemetry._InertInstrument)
        cache = AtlasCache(AtlasPolicy())
        resolved = cache.resolve_tiles(tiles={"a": tile("a", shade=15)})
        assert resolved.locations["a"].page_id
        telemetry.record_failure("SGC_ANY")
        with telemetry.measure("serialize_duration"):
            pass
    finally:
        telemetry.reset_instruments_for_tests()
