"""Content-Security-Policy requirements for graph-canvas transports."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from .model import Transport


def required_csp_directives(
    transports: Iterable[Transport] = (Transport.PRIMS,),
) -> dict[str, tuple[str, ...]]:
    """Return the additive CSP sources required by selected transports.

    These values are intended for the host application's reverse proxy or CSP
    middleware. The component cannot weaken or replace an enclosing page policy.
    """

    selected = set(transports)
    directives: dict[str, tuple[str, ...]] = {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'", "'unsafe-inline'"),
        "img-src": ("'self'", "data:"),
        "connect-src": ("'self'", "ws:", "wss:"),
        "font-src": ("'self'",),
        "object-src": ("'none'",),
        "base-uri": ("'none'",),
        "form-action": ("'self'",),
        "frame-ancestors": ("'self'",),
        "manifest-src": ("'self'",),
        "media-src": ("'self'",),
        "worker-src": ("'self'",),
    }
    if Transport.ATLAS in selected or Transport.RASTER in selected:
        directives["img-src"] = (*directives["img-src"], "blob:")
    # JavaScript renderer modules are packaged and same-origin. In particular,
    # the transport never requires unsafe-eval, data:, blob:, or remote scripts.
    return directives


def format_csp(transports: Iterable[Transport] = (Transport.PRIMS,)) -> str:
    """Format the required directives as a deterministic policy string."""

    return "; ".join(
        f"{directive} {' '.join(sources)}"
        for directive, sources in required_csp_directives(transports).items()
    )


def streamlit_host_csp(
    transports: Iterable[Transport] = (Transport.PRIMS,),
    *,
    app_origin: str | None = None,
    frame_ancestors: Iterable[str] = ("'self'",),
) -> str:
    """Return the tested full Streamlit host policy for the selected transports."""

    directives = required_csp_directives(transports)
    websocket_sources = (
        ("ws:", "wss:") if app_origin is None else (_websocket_origin(app_origin),)
    )
    directives["script-src"] = (
        "'self'",
        "'unsafe-inline'",
        "'wasm-unsafe-eval'",
    )
    directives["font-src"] = ("'self'", "data:")
    directives["connect-src"] = ("'self'", *websocket_sources)
    directives["frame-ancestors"] = _frame_ancestors(frame_ancestors)
    return "; ".join(
        f"{directive} {' '.join(sources)}" for directive, sources in directives.items()
    )


def _websocket_origin(app_origin: str) -> str:
    parsed = urlsplit(app_origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or "*" in app_origin
    ):
        raise ValueError("app_origin must be an exact HTTP(S) origin")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


def _frame_ancestors(values: Iterable[str]) -> tuple[str, ...]:
    sources = tuple(values)
    if not sources:
        raise ValueError("frame_ancestors must contain at least one source")
    if "'none'" in sources and sources != ("'none'",):
        raise ValueError("'none' cannot be combined with other frame ancestors")
    for source in sources:
        if source in {"'self'", "'none'"}:
            continue
        parsed = urlsplit(source)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "*" in source
        ):
            raise ValueError(
                "frame_ancestors entries must be 'self', 'none', or exact "
                "HTTP(S) origins"
            )
    return sources
