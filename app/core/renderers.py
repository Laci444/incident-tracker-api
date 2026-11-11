import json
from typing import Any

from dicttoxml2 import dicttoxml
from litestar import Request, Response

from app.core.exceptions import ProblemException

SUPPORTED_MEDIA_TYPES = (
    "application/hal+json",
    "application/json",
    "application/xml",
    "text/xml",
    "application/problem+json",
    "application/problem+xml",
)


def negotiate_media_type(request: Request) -> str:
    accept_header = request.headers.get("accept", "*/*").strip()
    if not accept_header or accept_header == "*/*":
        return "application/hal+json"

    candidates: list[tuple[float, str]] = []
    for raw_part in accept_header.split(","):
        segments = [s.strip() for s in raw_part.split(";") if s.strip()]
        if not segments:
            continue
        mime = segments[0].lower()
        q = 1.0
        for param in segments[1:]:
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        if q > 0:
            candidates.append((q, mime))

    # Sort by quality factor descending while preserving client preference order
    candidates.sort(key=lambda item: item[0], reverse=True)

    for _, mime in candidates:
        if mime in ("*/*", "application/*"):
            return "application/hal+json"
        if mime in SUPPORTED_MEDIA_TYPES:
            if mime in ("text/xml", "application/problem+xml"):
                return "application/xml"
            if mime == "application/problem+json":
                return "application/hal+json"
            return mime

    raise ProblemException(
        status_code=406,
        title="Not Acceptable",
        detail=(
            f"None of the requested media types in Accept ('{accept_header}') are supported. "
            "Supported types: application/hal+json, application/json, application/xml."
        ),
        type_slug="not-acceptable",
    )


def render_resource_response(
    request: Request,
    payload: dict[str, Any],
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    xml_root: str = "resource",
) -> Response:
    media_type = negotiate_media_type(request)
    response_headers = dict(headers or {})
    response_headers.setdefault("Vary", "Accept, Authorization")

    if media_type == "application/xml":
        body_bytes = dicttoxml(payload, custom_root=xml_root, attr_type=False)
    else:
        body_bytes = json.dumps(payload).encode("utf-8")

    # RFC 9110 Section 9.3.2: HEAD response must match GET headers (including Content-Length) with empty body
    if request.method == "HEAD":
        response_headers["Content-Length"] = str(len(body_bytes))
        body_bytes = b""

    return Response(
        content=body_bytes,
        status_code=status_code,
        media_type=media_type,
        headers=response_headers,
    )
