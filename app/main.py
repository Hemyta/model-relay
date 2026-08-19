import hmac
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from app import __version__
from app.docs import openapi, swagger_ui
from app.upstreams import UPSTREAMS


RELAY_TOKEN_HEADER = b"x-relay-token"
UPSTREAM_HEADER = b"x-relay-upstream"
HOP_BY_HOP_HEADERS = {
    b"connection",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailer",
    b"transfer-encoding",
    b"upgrade",
}


@dataclass(frozen=True)
class Settings:
    relay_token: str

    @classmethod
    def from_env(cls) -> "Settings":
        relay_token = os.environ.get("RELAY_TOKEN", "")
        if not relay_token:
            raise RuntimeError("RELAY_TOKEN must be set")

        return cls(relay_token=relay_token)


def _connection_headers(headers: list[tuple[bytes, bytes]]) -> set[bytes]:
    excluded: set[bytes] = set()
    for name, value in headers:
        if name.lower() == b"connection":
            excluded.update(part.strip().lower() for part in value.split(b",") if part.strip())
    return excluded


def _request_headers(request: Request) -> list[tuple[bytes, bytes]]:
    raw_headers = list(request.scope["headers"])
    excluded = HOP_BY_HOP_HEADERS | _connection_headers(raw_headers) | {
        b"host",
        RELAY_TOKEN_HEADER,
        UPSTREAM_HEADER,
    }
    return [(name, value) for name, value in raw_headers if name.lower() not in excluded]


def _response_headers(response: httpx.Response) -> list[tuple[bytes, bytes]]:
    raw_headers = list(response.headers.raw)
    excluded = HOP_BY_HOP_HEADERS | _connection_headers(raw_headers)
    return [(name, value) for name, value in raw_headers if name.lower() not in excluded]


async def health(_: Request) -> Response:
    return Response(status_code=204)


async def version(_: Request) -> JSONResponse:
    return JSONResponse({"version": __version__})


async def relay(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    supplied_token = request.headers.get(RELAY_TOKEN_HEADER.decode(), "")
    if not hmac.compare_digest(supplied_token, settings.relay_token):
        return Response(status_code=401)

    upstream_name = request.headers.get(UPSTREAM_HEADER.decode())
    base_url = UPSTREAMS.get(upstream_name or "")
    if base_url is None:
        return Response(status_code=400)

    raw_path = request.scope.get("raw_path", request.url.path.encode("ascii"))
    upstream_url = httpx.URL(base_url)
    target_path = upstream_url.raw_path.rstrip(b"/") + raw_path
    query_string = request.scope["query_string"]
    if query_string:
        target_path += b"?" + query_string
    target_url = upstream_url.copy_with(raw_path=target_path)

    client: httpx.AsyncClient = request.app.state.client
    upstream_request = client.build_request(
        method=request.method,
        url=target_url,
        headers=_request_headers(request),
        content=request.stream(),
    )
    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.RequestError:
        return Response(status_code=502)

    response = StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        background=BackgroundTask(upstream_response.aclose),
    )
    response.raw_headers = _response_headers(upstream_response)
    return response


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    settings = Settings.from_env()
    timeout = httpx.Timeout(
        connect=10,
        read=300,
        write=300,
        pool=10,
    )
    app.state.settings = settings
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        app.state.client = client
        yield


app = Starlette(
    routes=[
        Route("/healthz", health, methods=["GET"]),
        Route("/version", version, methods=["GET"]),
        Route("/docs", swagger_ui, methods=["GET"]),
        Route("/openapi.json", openapi, methods=["GET"]),
        Route("/{path:path}", relay, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
    ],
    lifespan=lifespan,
)