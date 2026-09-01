"""Run Streamlit behind the CSP response-header reverse proxy used in CI."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
from streamlit_graph_canvas import Transport, streamlit_host_csp
from websockets.asyncio.client import connect

UPSTREAM_HTTP = "http://127.0.0.1:8513"
UPSTREAM_WS = "ws://127.0.0.1:8513"
PROXY_ORIGIN = "http://127.0.0.1:8514"
CSP = streamlit_host_csp(
    (Transport.PRIMS, Transport.JAVASCRIPT, Transport.ATLAS),
    app_origin=PROXY_ORIGIN,
)


def _http_request(
    method: str, path: str, headers: list[tuple[bytes, bytes]], body: bytes
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    forwarded = {
        key.decode("latin1"): value.decode("latin1")
        for key, value in headers
        if key.lower() not in {b"host", b"connection", b"content-length"}
    }
    request = urllib.request.Request(
        UPSTREAM_HTTP + path, data=body or None, headers=forwarded, method=method
    )
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        payload = response.read()
        response_headers = [
            (key.encode("latin1"), value.encode("latin1"))
            for key, value in response.headers.items()
            if key.casefold()
            not in {"connection", "transfer-encoding", "content-length"}
        ]
        response_headers.extend(
            [
                (b"content-length", str(len(payload)).encode()),
                (b"content-security-policy", CSP.encode()),
            ]
        )
        return response.status, response_headers, payload


async def _proxy_http(scope, receive, send) -> None:
    chunks = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    path = scope["raw_path"].decode("latin1")
    if scope["query_string"]:
        path += "?" + scope["query_string"].decode("latin1")
    status, headers, body = await asyncio.to_thread(
        _http_request, scope["method"], path, scope["headers"], b"".join(chunks)
    )
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _proxy_websocket(scope, receive, send) -> None:
    path = scope["raw_path"].decode("latin1")
    if scope["query_string"]:
        path += "?" + scope["query_string"].decode("latin1")
    headers = {
        key.decode("latin1"): value.decode("latin1")
        for key, value in scope["headers"]
        if key.lower() not in {b"host", b"connection", b"upgrade", b"origin"}
    }
    await receive()
    async with connect(
        UPSTREAM_WS + path,
        additional_headers=headers,
        origin=PROXY_ORIGIN,
    ) as upstream:
        await send({"type": "websocket.accept"})

        async def client_to_upstream() -> None:
            while True:
                message = await receive()
                if message["type"] == "websocket.disconnect":
                    await upstream.close()
                    return
                await upstream.send(message.get("text", message.get("bytes")))

        async def upstream_to_client() -> None:
            async for message in upstream:
                key = "text" if isinstance(message, str) else "bytes"
                await send({"type": "websocket.send", key: message})

        await asyncio.gather(client_to_upstream(), upstream_to_client())


async def app(scope, receive, send) -> None:
    if scope["type"] == "http":
        await _proxy_http(scope, receive, send)
    elif scope["type"] == "websocket":
        await _proxy_websocket(scope, receive, send)


def main() -> None:
    root = Path(__file__).parents[2]
    runner = root / "tests/e2e/run_streamlit.py"
    streamlit = subprocess.Popen([sys.executable, str(runner)])
    try:
        for attempt in range(120):
            if streamlit.poll() is not None:
                raise RuntimeError("Streamlit exited before the CSP proxy started")
            try:
                with urllib.request.urlopen(
                    f"{UPSTREAM_HTTP}/_stcore/health", timeout=1
                ) as response:
                    if response.status == 200:
                        break
            except urllib.error.URLError:
                if attempt == 119:
                    raise RuntimeError("Streamlit health check timed out") from None
                time.sleep(0.25)
        uvicorn.run(app, host="127.0.0.1", port=8514, log_level="info")
    finally:
        streamlit.terminate()
        streamlit.wait(timeout=15)


if __name__ == "__main__":
    main()
