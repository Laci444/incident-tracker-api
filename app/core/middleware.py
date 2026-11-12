import re

from litestar import Request
from litestar.middleware import AbstractMiddleware
from litestar.routes import HTTPRoute
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from app.config import API_CSP_HEADER, SWAGGER_CSP_HEADER
from app.core.enums import ApiPath, HttpHeader, HttpMethod, MediaType
from app.core.exceptions import (
    ProblemException,
    UnsupportedMediaTypeError,
    problem_exception_handler,
)
from app.core.renderers import current_request_var, negotiate_media_type

_CANONICAL_METHOD_ORDER: tuple[str, ...] = (
    HttpMethod.GET.value,
    HttpMethod.HEAD.value,
    HttpMethod.POST.value,
    HttpMethod.PUT.value,
    HttpMethod.PATCH.value,
    HttpMethod.DELETE.value,
    HttpMethod.OPTIONS.value,
)


def _discover_route_options(request: Request) -> tuple[str, bool] | None:
    """Dynamically inspects registered Litestar routes to determine Allow and Accept-Patch headers."""
    target_path = request.url.path.rstrip("/") or "/"

    for route in request.app.routes:
        if not isinstance(route, HTTPRoute):
            continue
        route_path = route.path.rstrip("/") or "/"
        pattern_str = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", route_path) + "$"
        if re.match(pattern_str, target_path):
            registered = {m.upper() for m in route.methods} | {HttpMethod.OPTIONS.value}
            if HttpMethod.GET.value in registered:
                registered.add(HttpMethod.HEAD.value)
            ordered = [m for m in _CANONICAL_METHOD_ORDER if m in registered]
            supports_patch = HttpMethod.PATCH.value in registered
            return ", ".join(ordered), supports_patch

    return None


class SecurityHeadersMiddleware(AbstractMiddleware):
    """Attaches strict Content-Security-Policy to API responses and relaxed CSP to Swagger UI."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app=app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        csp_value = (
            SWAGGER_CSP_HEADER
            if path.startswith(ApiPath.SCHEMA_ROOT.value)
            else API_CSP_HEADER
        )
        csp_header_bytes = HttpHeader.CONTENT_SECURITY_POLICY.lower().encode("latin-1")

        async def send_with_csp(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                if not any(k.lower() == csp_header_bytes for k, _ in raw_headers):
                    raw_headers.append((csp_header_bytes, csp_value.encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_with_csp)


class ProtocolNegotiationMiddleware(AbstractMiddleware):
    """Enforces Accept (406), Content-Type (415), and dynamic OPTIONS headers across API routes."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app=app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope, receive=receive)
        token = current_request_var.set(request)
        path = request.url.path
        method = request.method.upper()

        try:
            if path.startswith(ApiPath.ROOT.value):
                if method != HttpMethod.OPTIONS.value:
                    negotiate_media_type(request)

                if method in (HttpMethod.POST.value, HttpMethod.PUT.value):
                    content_type = (
                        request.headers.get(HttpHeader.CONTENT_TYPE.lower(), "")
                        .split(";")[0]
                        .strip()
                        .lower()
                    )
                    if content_type != MediaType.JSON.value:
                        raise UnsupportedMediaTypeError(
                            f"HTTP {method} requires '{HttpHeader.CONTENT_TYPE.value}: {MediaType.JSON.value}'."
                        )
                elif method == HttpMethod.PATCH.value:
                    content_type = (
                        request.headers.get(HttpHeader.CONTENT_TYPE.lower(), "")
                        .split(";")[0]
                        .strip()
                        .lower()
                    )
                    if content_type != MediaType.MERGE_PATCH_JSON.value:
                        raise UnsupportedMediaTypeError(
                            f"HTTP {HttpMethod.PATCH.value} requires "
                            f"'{HttpHeader.CONTENT_TYPE.value}: {MediaType.MERGE_PATCH_JSON.value}' (RFC 7396).",
                            advertise_merge_patch=True,
                        )

            options_meta = (
                _discover_route_options(request)
                if method == HttpMethod.OPTIONS.value
                else None
            )

            async def send_with_options_headers(message: Message) -> None:
                if (
                    message["type"] == "http.response.start"
                    and options_meta is not None
                ):
                    allow_val, supports_patch = options_meta
                    allow_key = HttpHeader.ALLOW.lower().encode("latin-1")
                    patch_key = HttpHeader.ACCEPT_PATCH.lower().encode("latin-1")
                    raw_headers = [
                        (k, v)
                        for k, v in message.get("headers", [])
                        if k.lower() not in (allow_key, patch_key)
                    ]
                    raw_headers.append((allow_key, allow_val.encode("latin-1")))
                    if supports_patch:
                        raw_headers.append(
                            (
                                patch_key,
                                MediaType.MERGE_PATCH_JSON.value.encode("latin-1"),
                            )
                        )
                    message["headers"] = raw_headers
                await send(message)

            await self.app(scope, receive, send_with_options_headers)

        except ProblemException as exc:
            error_response = problem_exception_handler(request, exc)
            asgi_response = error_response.to_asgi_response(app=None, request=request)
            await asgi_response(scope, receive, send)
        finally:
            current_request_var.reset(token)
