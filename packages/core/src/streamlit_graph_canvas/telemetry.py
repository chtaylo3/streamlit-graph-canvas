"""OpenTelemetry metrics for operators of the canvas.

The package depends on ``opentelemetry-api`` only, never the SDK, so it never
competes with the application's own telemetry configuration. Telemetry flows to
whichever provider the application installs. When no provider is configured, or
when the ``otel`` extra is not installed at all, every instrument here is inert
and no call raises.

Metric names and attributes are covered by the module's semantic versioning, and
a breaking change in OpenTelemetry is a breaking change of this module. The
metrics are intended for engineers and developers operating the component rather
than as an application-facing API.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

METER_NAME = "streamlit_graph_canvas"

# Seconds, following the OpenTelemetry convention for duration histograms.
_DURATION_UNIT = "s"


class _Counter(Protocol):
    def add(self, amount: int, attributes: Mapping[str, Any] | None = ...) -> None: ...


class _Histogram(Protocol):
    def record(
        self, amount: float, attributes: Mapping[str, Any] | None = ...
    ) -> None: ...


class _InertInstrument:
    """Stand-in used when ``opentelemetry-api`` is not installed."""

    def add(self, amount: int, attributes: Mapping[str, Any] | None = None) -> None:
        return None

    def record(
        self, amount: float, attributes: Mapping[str, Any] | None = None
    ) -> None:
        return None


@dataclass(frozen=True, slots=True)
class _Instruments:
    tile_lookups: _Counter
    pages_evicted: _Counter
    failures: _Counter
    pages_resident: _Counter
    bytes_resident: _Counter
    pack_duration: _Histogram
    serialize_duration: _Histogram


def _inert() -> _Instruments:
    instrument = _InertInstrument()
    return _Instruments(
        tile_lookups=instrument,
        pages_evicted=instrument,
        failures=instrument,
        pages_resident=instrument,
        bytes_resident=instrument,
        pack_duration=instrument,
        serialize_duration=instrument,
    )


@lru_cache(maxsize=1)
def instruments() -> _Instruments:
    """Return the process instruments, building them on first use.

    ``get_meter`` yields a no-op meter until the application installs a provider,
    so this stays cheap and side-effect free in an unconfigured process.
    """

    try:
        from opentelemetry import metrics
    except ImportError:
        return _inert()

    from . import __version__

    meter = metrics.get_meter(METER_NAME, __version__)
    return _Instruments(
        tile_lookups=meter.create_counter(
            "sgc.atlas.tile.lookups",
            unit="{lookup}",
            description="Atlas tile lookups, split by cache result.",
        ),
        pages_evicted=meter.create_counter(
            "sgc.atlas.pages.evicted",
            unit="{page}",
            description="Atlas pages evicted to stay within the configured limits.",
        ),
        failures=meter.create_counter(
            "sgc.atlas.failures",
            unit="{failure}",
            description="Atlas resolutions that failed closed, by diagnostic code.",
        ),
        pages_resident=meter.create_up_down_counter(
            "sgc.atlas.pages.resident",
            unit="{page}",
            description="Atlas pages currently held in the process cache.",
        ),
        bytes_resident=meter.create_up_down_counter(
            "sgc.atlas.bytes.resident",
            unit="By",
            description="Encoded atlas bytes currently held in the process cache.",
        ),
        pack_duration=meter.create_histogram(
            "sgc.atlas.pack.duration",
            unit=_DURATION_UNIT,
            description="Time spent rasterizing and packing missing atlas tiles.",
        ),
        serialize_duration=meter.create_histogram(
            "sgc.serialize.duration",
            unit=_DURATION_UNIT,
            description="Time spent building a canvas envelope.",
        ),
    )


def reset_instruments_for_tests() -> None:
    """Drop the cached instruments so a test can install a fresh provider."""

    instruments.cache_clear()


def record_tile_lookups(*, hits: int, misses: int) -> None:
    if hits:
        instruments().tile_lookups.add(hits, {"result": "hit"})
    if misses:
        instruments().tile_lookups.add(misses, {"result": "miss"})


def record_eviction(pages: int, released_bytes: int) -> None:
    if not pages:
        return
    instruments().pages_evicted.add(pages)


def record_residency(*, pages_delta: int, bytes_delta: int) -> None:
    if pages_delta:
        instruments().pages_resident.add(pages_delta)
    if bytes_delta:
        instruments().bytes_resident.add(bytes_delta)


def record_failure(code: str) -> None:
    instruments().failures.add(1, {"code": code})


@contextmanager
def measure(histogram_name: str) -> Iterator[None]:
    """Record wall-clock seconds for a block into the named histogram."""

    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        histogram = getattr(instruments(), histogram_name)
        histogram.record(elapsed)
