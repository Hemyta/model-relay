import os
import unittest
from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

from app import __version__
from app.main import UPSTREAMS, app


class RecordingClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = httpx.Response(
            response.status_code,
            headers=response.headers.raw,
            stream=httpx.ByteStream(response.content),
        )
        self.requests: list[httpx.Request] = []

    def build_request(self, *args: object, **kwargs: object) -> httpx.Request:
        return httpx.Request(*args, **kwargs)

    async def send(self, request: httpx.Request, *, stream: bool) -> httpx.Response:
        if not stream:
            raise AssertionError("The upstream response must be streamed")
        await request.aread()
        self.requests.append(request)
        self.response.request = request
        return self.response


class RelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {"RELAY_TOKEN": "relay-secret"})
        self.environment.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.environment.stop()

    def test_forwards_request_without_relay_control_headers(self) -> None:
        upstream = RecordingClient(
            httpx.Response(
                200,
                headers=[("content-type", "application/octet-stream"), ("x-upstream", "yes")],
                content=b"\x00response\xff",
            )
        )
        app.state.client = upstream

        response = self.client.post(
            "/models/gemini-3.1-flash-lite:generateContent?key=provider-key&alt=sse",
            headers={
                "X-Relay-Token": "relay-secret",
                "X-Relay-Upstream": "gemini",
                "Authorization": "Bearer provider-token",
                "X-Goog-Api-Key": "provider-key",
                "Content-Type": "application/json",
            },
            content=b'{"contents":[]}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"\x00response\xff")
        self.assertEqual(response.headers["x-upstream"], "yes")
        request = upstream.requests[0]
        self.assertEqual(
            str(request.url),
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-3.1-flash-lite:generateContent?key=provider-key&alt=sse",
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.content, b'{"contents":[]}')
        self.assertEqual(request.headers["authorization"], "Bearer provider-token")
        self.assertEqual(request.headers["x-goog-api-key"], "provider-key")
        self.assertNotIn("x-relay-token", request.headers)
        self.assertNotIn("x-relay-upstream", request.headers)

    def test_preserves_upstream_error_response(self) -> None:
        upstream = RecordingClient(
            httpx.Response(
                429,
                headers={"content-type": "application/json", "retry-after": "15"},
                content=b'{"error":"quota exceeded"}',
            )
        )
        app.state.client = upstream

        response = self.client.get(
            "/models",
            headers={"X-Relay-Token": "relay-secret", "X-Relay-Upstream": "gemini"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content, b'{"error":"quota exceeded"}')
        self.assertEqual(response.headers["retry-after"], "15")

    def test_requires_explicit_configured_upstream(self) -> None:
        upstream = RecordingClient(httpx.Response(204))
        app.state.client = upstream

        missing = self.client.get("/models", headers={"X-Relay-Token": "relay-secret"})
        rejected = self.client.get(
            "/models",
            headers={"X-Relay-Token": "relay-secret", "X-Relay-Upstream": "unconfigured"},
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(upstream.requests, [])

    def test_supports_additional_configured_upstreams(self) -> None:
        upstream = RecordingClient(httpx.Response(204))
        app.state.client = upstream

        with patch.dict(UPSTREAMS, {"other": "https://api.example.com/v1"}):
            response = self.client.get(
                "/models",
                headers={"X-Relay-Token": "relay-secret", "X-Relay-Upstream": "other"},
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(str(upstream.requests[0].url), "https://api.example.com/v1/models")

    def test_rejects_missing_or_invalid_relay_token(self) -> None:
        upstream = RecordingClient(httpx.Response(204))
        app.state.client = upstream

        self.assertEqual(self.client.get("/models").status_code, 401)
        self.assertEqual(
            self.client.get("/models", headers={"X-Relay-Token": "wrong"}).status_code,
            401,
        )
        self.assertEqual(upstream.requests, [])

    def test_health_check_does_not_require_authentication(self) -> None:
        self.assertEqual(self.client.get("/healthz").status_code, 204)

    def test_exposes_service_version(self) -> None:
        version_response = self.client.get("/version")
        schema_response = self.client.get("/openapi.json")

        self.assertEqual(version_response.status_code, 200)
        self.assertEqual(version_response.json(), {"version": __version__})
        self.assertEqual(schema_response.json()["info"]["version"], __version__)

    def test_serves_swagger_api_documentation(self) -> None:
        docs_response = self.client.get("/docs")
        schema_response = self.client.get("/openapi.json")

        self.assertEqual(docs_response.status_code, 200)
        self.assertIn("SwaggerUIBundle", docs_response.text)
        self.assertEqual(schema_response.status_code, 200)
        schema = schema_response.json()
        self.assertIn("/models/{model_action}", schema["paths"])
        self.assertEqual(
            schema["components"]["securitySchemes"]["relayToken"]["name"],
            "X-Relay-Token",
        )


if __name__ == "__main__":
    unittest.main()