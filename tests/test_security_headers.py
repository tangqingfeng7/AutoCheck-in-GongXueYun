import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse, Response


class FakeStreamingRequest:
    def __init__(self, *, method="POST", headers=None, chunks=None):
        self.method = method
        self.headers = headers or {}
        self._chunks = list(chunks or [])

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


class SecurityHeadersTest(unittest.TestCase):
    def test_default_security_headers_include_csp(self):
        from server.security import apply_security_headers

        response = Response()

        apply_security_headers(response)

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("frame-src 'self' https://www.openstreetmap.org", response.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_hsts_can_be_enabled_for_https_deployments(self):
        from server.security import apply_security_headers

        response = Response()

        with patch.dict("os.environ", {"ENABLE_HSTS": "true"}, clear=False):
            apply_security_headers(response)

        self.assertIn("max-age=", response.headers["Strict-Transport-Security"])

    def test_hsts_is_enabled_by_default_in_production_and_can_be_disabled(self):
        from server.security import apply_security_headers

        production_response = Response()
        disabled_response = Response()

        with patch.dict("os.environ", {"APP_ENV": "production", "ENABLE_HSTS": ""}, clear=False):
            apply_security_headers(production_response)
        with patch.dict("os.environ", {"APP_ENV": "production", "ENABLE_HSTS": "false"}, clear=False):
            apply_security_headers(disabled_response)

        self.assertIn("max-age=", production_response.headers["Strict-Transport-Security"])
        self.assertNotIn("Strict-Transport-Security", disabled_response.headers)

    def test_metrics_requires_token_in_production(self):
        from server.security import require_metrics_access

        request = SimpleNamespace(headers={})

        with patch.dict("os.environ", {"APP_ENV": "production", "METRICS_AUTH_TOKEN": ""}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                require_metrics_access(request)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_metrics_accepts_configured_token(self):
        from server.security import require_metrics_access

        request = SimpleNamespace(headers={"x-metrics-token": "secret-token"})

        with patch.dict("os.environ", {"APP_ENV": "production", "METRICS_AUTH_TOKEN": "secret-token"}, clear=False):
            self.assertIsNone(require_metrics_access(request))

    def test_api_docs_are_disabled_by_default_in_production(self):
        from server.main import _should_expose_api_docs

        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=False):
            self.assertFalse(_should_expose_api_docs())
        with patch.dict("os.environ", {"APP_ENV": "development"}, clear=False):
            self.assertTrue(_should_expose_api_docs())

    def test_wildcard_cors_is_rejected_in_production_by_default(self):
        from server.main import _resolve_cors_origins

        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "FRONTEND_ORIGINS": "*", "ALLOW_WILDCARD_CORS": ""},
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                _resolve_cors_origins()

        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "FRONTEND_ORIGINS": "*", "ALLOW_WILDCARD_CORS": "true"},
            clear=False,
        ):
            self.assertEqual(_resolve_cors_origins(), ["*"])

    def test_request_body_limit_defaults_to_disabled_in_development(self):
        from server.main import _max_request_body_bytes, _request_body_too_large

        with patch.dict("os.environ", {"APP_ENV": "development", "MAX_REQUEST_BODY_BYTES": ""}, clear=False):
            limit = _max_request_body_bytes()
            self.assertEqual(limit, 0)
            self.assertFalse(_request_body_too_large(SimpleNamespace(method="POST", headers={"content-length": "2048"}), limit))

    def test_request_body_limit_uses_configured_limit_and_detects_large_payloads(self):
        from server.main import _max_request_body_bytes, _request_body_too_large

        with patch.dict("os.environ", {"APP_ENV": "production", "MAX_REQUEST_BODY_BYTES": "1024"}, clear=False):
            self.assertEqual(_max_request_body_bytes(), 1024)
            self.assertTrue(_request_body_too_large(SimpleNamespace(method="POST", headers={"content-length": "2048"}), 1024))

    def test_streaming_request_body_limit_rejects_chunked_large_payloads(self):
        from server.main import _cache_request_body_with_limit

        request = FakeStreamingRequest(headers={}, chunks=[b"a" * 600, b"b" * 600])

        too_large = asyncio.run(_cache_request_body_with_limit(request, 1024))

        self.assertTrue(too_large)

    def test_streaming_request_body_limit_caches_safe_payloads_for_downstream(self):
        from server.main import _cache_request_body_with_limit

        request = FakeStreamingRequest(headers={}, chunks=[b"abc", b"def"])

        too_large = asyncio.run(_cache_request_body_with_limit(request, 1024))

        self.assertFalse(too_large)
        self.assertEqual(request._body, b"abcdef")

    def test_request_body_limit_keeps_safe_body_readable_by_endpoint(self):
        from server.main import _cache_request_body_with_limit

        app = FastAPI()

        @app.middleware("http")
        async def body_limit(request, call_next):
            if await _cache_request_body_with_limit(request, 8):
                return JSONResponse(status_code=413, content={"detail": "too large"})
            return await call_next(request)

        @app.post("/echo-size")
        async def echo_size(request: Request):
            return {"size": len(await request.body())}

        client = TestClient(app)

        self.assertEqual(client.post("/echo-size", content=b"abcdef").json(), {"size": 6})
        self.assertEqual(client.post("/echo-size", content=b"abcdefghi").status_code, 413)

    def test_trusted_hosts_are_loaded_from_env(self):
        from server.main import _resolve_trusted_hosts

        with patch.dict("os.environ", {"TRUSTED_HOSTS": "api.example.com, admin.example.com"}, clear=False):
            self.assertEqual(_resolve_trusted_hosts(), ["api.example.com", "admin.example.com"])

    def test_trusted_hosts_fall_back_to_cors_origins(self):
        from server.main import _resolve_trusted_hosts

        with patch.dict(
            "os.environ",
            {"TRUSTED_HOSTS": "", "FRONTEND_ORIGINS": "https://admin.example.com,https://app.example.com:8443"},
            clear=False,
        ):
            self.assertEqual(_resolve_trusted_hosts(), ["admin.example.com", "app.example.com"])

    def test_trusted_hosts_fail_closed_in_production_when_missing(self):
        from server.main import _resolve_trusted_hosts

        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "TRUSTED_HOSTS": "", "FRONTEND_ORIGINS": "", "CORS_ORIGINS": ""},
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                _resolve_trusted_hosts()


if __name__ == "__main__":
    unittest.main()
