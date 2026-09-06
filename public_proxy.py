from __future__ import annotations

import asyncio
import os
import time
from urllib.parse import urlsplit

import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

UPSTREAM = os.environ.get("JJ_UPSTREAM_URL", "https://jj-arena-live.onrender.com").rstrip("/")
UPSTREAM_WS = ("wss://" if UPSTREAM.startswith("https://") else "ws://") + urlsplit(UPSTREAM).netloc
UPSTREAM_ORIGIN = UPSTREAM

app = FastAPI(title="JJ Arena Public Gateway", docs_url=None, redoc_url=None, openapi_url=None)

# httpx transparently decodes compressed upstream bodies. Never forward the
# original Content-Encoding afterward, and do not request compression upstream.
REQUEST_STRIP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "accept-encoding",
}
RESPONSE_STRIP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "content-encoding",
}

# Both Render services are currently on the free plan and may sleep. When the
# gateway wakes first, Render can return a temporary 502/503/504 for the still-
# sleeping upstream. Safe/read-only requests wait for the upstream to wake
# instead of exposing that transient platform error to the browser.
COLD_START_STATUSES = {502, 503, 504}
SAFE_RETRY_METHODS = {"GET", "HEAD", "OPTIONS"}
COLD_START_BUDGET_SECONDS = 55.0
COLD_START_RETRY_DELAY_SECONDS = 1.5


def _request_headers(request: Request) -> dict[str, str]:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in REQUEST_STRIP}
    if "origin" in headers:
        headers["origin"] = UPSTREAM_ORIGIN
    if "referer" in headers:
        headers["referer"] = UPSTREAM_ORIGIN + "/"
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = request.url.scheme
    return headers


def _response_headers(response: httpx.Response) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, value in response.headers.multi_items():
        if key.lower() not in RESPONSE_STRIP:
            out.append((key, value))
    return out


async def _upstream_request(method: str, target: str, body: bytes, headers: dict[str, str]) -> httpx.Response:
    retryable = method.upper() in SAFE_RETRY_METHODS
    deadline = time.monotonic() + COLD_START_BUDGET_SECONDS
    last_response: httpx.Response | None = None
    last_error: Exception | None = None

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(20.0, connect=12.0),
    ) as client:
        while True:
            try:
                response = await client.request(method, target, content=body, headers=headers)
                last_response = response
                last_error = None
                if not retryable or response.status_code not in COLD_START_STATUSES:
                    return response
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_error = exc
                if not retryable:
                    raise

            if not retryable or time.monotonic() >= deadline:
                if last_response is not None:
                    return last_response
                if last_error is not None:
                    raise last_error
                raise RuntimeError("upstream unavailable")
            await asyncio.sleep(COLD_START_RETRY_DELAY_SECONDS)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_http(path: str, request: Request):
    target = f"{UPSTREAM}/{path}"
    if request.url.query:
        target += "?" + request.url.query
    body = await request.body()
    try:
        upstream = await _upstream_request(
            request.method,
            target,
            body,
            _request_headers(request),
        )
    except (httpx.HTTPError, RuntimeError):
        return Response(
            content="JJ Arena is waking up. Please retry shortly.",
            status_code=503,
            media_type="text/plain; charset=utf-8",
            headers={"Retry-After": "3", "Cache-Control": "no-store"},
        )

    response = Response(content=upstream.content, status_code=upstream.status_code, media_type=None)
    for key, value in _response_headers(upstream):
        response.headers.append(key, value)
    return response


async def _connect_upstream_ws(upstream_url: str, headers: dict[str, str]):
    deadline = time.monotonic() + COLD_START_BUDGET_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return await websockets.connect(
                upstream_url,
                origin=UPSTREAM_ORIGIN,
                additional_headers=headers,
                open_timeout=12,
                ping_interval=20,
                ping_timeout=20,
            )
        except Exception as exc:
            last_error = exc
            # Wake the HTTP service too; this is useful when Render has not yet
            # started the upstream instance for a direct WebSocket handshake.
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=6.0)) as client:
                    await client.get(UPSTREAM + "/api/health")
            except Exception:
                pass
            await asyncio.sleep(COLD_START_RETRY_DELAY_SECONDS)
    if last_error is not None:
        raise last_error
    raise RuntimeError("upstream websocket unavailable")


@app.websocket("/ws/{path:path}")
async def proxy_websocket(client_ws: WebSocket, path: str):
    await client_ws.accept()
    upstream_url = f"{UPSTREAM_WS}/ws/{path}"
    cookie = client_ws.headers.get("cookie")
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    try:
        upstream_ws = await _connect_upstream_ws(upstream_url, headers)
        async with upstream_ws:
            async def client_to_upstream():
                while True:
                    msg = await client_ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    if msg.get("text") is not None:
                        await upstream_ws.send(msg["text"])
                    elif msg.get("bytes") is not None:
                        await upstream_ws.send(msg["bytes"])

            async def upstream_to_client():
                async for msg in upstream_ws:
                    if isinstance(msg, bytes):
                        await client_ws.send_bytes(msg)
                    else:
                        await client_ws.send_text(msg)

            _, pending = await asyncio.wait(
                [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        pass
    except Exception:
        try:
            await client_ws.close(code=1011)
        except Exception:
            pass
