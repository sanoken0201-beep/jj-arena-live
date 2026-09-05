from __future__ import annotations

import asyncio
import os
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


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_http(path: str, request: Request):
    target = f"{UPSTREAM}/{path}"
    if request.url.query:
        target += "?" + request.url.query
    body = await request.body()
    async with httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(60.0, connect=20.0)) as client:
        upstream = await client.request(
            request.method,
            target,
            content=body,
            headers=_request_headers(request),
        )
    response = Response(content=upstream.content, status_code=upstream.status_code, media_type=None)
    for key, value in _response_headers(upstream):
        response.headers.append(key, value)
    return response


@app.websocket("/ws/{path:path}")
async def proxy_websocket(client_ws: WebSocket, path: str):
    await client_ws.accept()
    upstream_url = f"{UPSTREAM_WS}/ws/{path}"
    cookie = client_ws.headers.get("cookie")
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    try:
        async with websockets.connect(
            upstream_url,
            origin=UPSTREAM_ORIGIN,
            additional_headers=headers,
            open_timeout=20,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream_ws:
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
