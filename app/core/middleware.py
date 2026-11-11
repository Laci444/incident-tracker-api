import re

from litestar import Request
from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from app.config import API_CSP_HEADER, SWAGGER_CSP_HEADER
from app.core.exceptions import ProblemException, problem_exception_handler
from app.core.renderers import negotiate_media_type

_OPTIONS_RULES: list[tuple[re.Pattern[str], str, bool]] = [
    (re.compile(r"^/api/?$"), "GET, HEAD, OPTIONS", False),
    (re.compile(r"^/api/me/?$"), "GET, HEAD, OPTIONS", False),
    (re.compile(r"^/api/services/?$"), "GET, HEAD, POST, OPTIONS", False),
    (re.compile(r"^/api/services/\d+/?$"), "GET, HEAD, PUT, PATCH, DELETE, OPTIONS", True),
    (re.compile(r"^/api/services/\d+/releases/?$"), "GET, HEAD, POST, OPTIONS", False),
    (re.compile(r"^/api/releases/\d+/?$"), "GET, HEAD, PATCH, DELETE, OPTIONS", True),
    (re.compile(r"^/api/incidents/?$"), "GET, HEAD, POST, OPTIONS", False),
    (re.compile(r"^/api/incidents/\d+/?$"), "GET, HEAD, PUT, PATCH, DELETE, OPTIONS", True),
]


def _resolve_options_metadata(path: str) -> tuple[str, bool] | None:
    for pattern, allow_value, supports_patch in _OPTIONS_RULES:
        if pattern.match(path):
            return allow_value, supports_patch
    return None


class ProtocolComplianceMiddleware(AbstractMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app=app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope, receive=receive)
        path = request.url.path
        method = request.method.upper()

        try:
            if path.startswith("/api"):
                if method != "OPTIONS":
                    negotiate_media_type(request)

                if method in ("POST", "PUT"):
                    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type != "application/json":
                        raise ProblemException(
                            status_code=415,
                            title="Unsupported Media Type",
                            detail=f"Method {method} requires 'Content-Type: application/json'.",
                            type_slug="unsupported-media-type",
                        )
                elif method == "PATCH":
                    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type != "application/merge-patch+json":
                        raise ProblemException(
                            status_code=415,
                            title="Unsupported Media Type",
                            detail="PATCH requests must use 'Content-Type: application/merge-patch+json' (RFC 7396).",
                            type_slug="invalid-patch-media-type",
                            headers={"Accept-Patch": "application/merge-patch+json"},
                        )
        except ProblemException as exc:
            error_response = problem_exception_handler(request, exc)
            asgi_response = error_response.to_asgi_response(app=None, request=request)
            await asgi_response(scope, receive, send)
            return

        csp_value = SWAGGER_CSP_HEADER if path.startswith("/schema") else API_CSP_HEADER
        options_meta = _resolve_options_metadata(path) if method == "OPTIONS" else None

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))

                if options_meta is not None:
                    allow_val, supports_patch = options_meta
                    raw_headers = [
                        (k, v)
                        for k, v in raw_headers
                        if k.lower() not in (b"allow", b"accept-patch")
                    ]
                    raw_headers.append((b"allow", allow_val.encode("latin-1")))
                    if supports_patch:
                        raw_headers.append((b"accept-patch", b"application/merge-patch+json"))

                has_csp = any(k.lower() == b"content-security-policy" for k, _ in raw_headers)
                if not has_csp:
                    raw_headers.append((b"content-security-policy", csp_value.encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
