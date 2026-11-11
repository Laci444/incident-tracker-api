import json
from http import HTTPStatus
from typing import Any

from dicttoxml2 import dicttoxml
from litestar import Request, Response
from litestar.exceptions import (
    HTTPException,
    MethodNotAllowedException,
    NotFoundException,
    ValidationException,
)


class ProblemException(Exception):
    """RFC 9457 Problem Details exception."""

    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        type_slug: str = "about:blank",
        headers: dict[str, str] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.type_slug = type_slug
        self.headers = headers or {}
        self.extensions = extensions or {}


def _wants_xml_problem(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    return "application/problem+xml" in accept or (
        "application/xml" in accept and "json" not in accept
    )


def problem_exception_handler(request: Request, exc: Exception) -> Response:
    status_code = 500
    title = "Internal Server Error"
    detail = "An unexpected error occurred while processing the request."
    type_uri = "https://iana.org/assignments/http-problem-types#internal-server-error"
    headers: dict[str, str] = {"Cache-Control": "no-store"}
    extensions: dict[str, Any] = {}

    if isinstance(exc, ProblemException):
        status_code = exc.status_code
        title = exc.title
        detail = exc.detail
        type_uri = (
            exc.type_slug
            if exc.type_slug.startswith("http") or exc.type_slug == "about:blank"
            else f"urn:problem-type:{exc.type_slug}"
        )
        headers.update(exc.headers)
        extensions.update(exc.extensions)

    elif isinstance(exc, ValidationException):
        status_code = 422
        title = "Unprocessable Content"
        detail = "Request payload or parameters failed schema validation."
        type_uri = "urn:problem-type:validation-error"
        extensions["errors"] = exc.extra or exc.detail

    elif isinstance(exc, MethodNotAllowedException):
        status_code = 405
        title = "Method Not Allowed"
        detail = f"HTTP method {request.method} is not allowed for {request.url.path}."
        type_uri = "urn:problem-type:method-not-allowed"
        if exc.headers:
            headers.update(exc.headers)

    elif isinstance(exc, NotFoundException):
        status_code = 404
        title = "Resource Not Found"
        detail = f"No resource found at URI '{request.url.path}'."
        type_uri = "urn:problem-type:not-found"

    elif isinstance(exc, HTTPException):
        status_code = exc.status_code
        try:
            title = HTTPStatus(status_code).phrase
        except ValueError:
            title = "HTTP Error"
        detail = str(exc.detail)
        type_uri = f"urn:problem-type:http-{status_code}"
        if exc.headers:
            headers.update(exc.headers)

    # RFC 9110 requires WWW-Authenticate on every 401 Unauthorized response
    if status_code == 401 and "WWW-Authenticate" not in headers:
        headers["WWW-Authenticate"] = (
            'Basic realm="IncidentReleaseAPI", charset="UTF-8"'
        )

    problem_body: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        **extensions,
    }

    if _wants_xml_problem(request):
        xml_bytes = dicttoxml(problem_body, custom_root="problem", attr_type=False)
        media_type = "application/problem+xml"
        content = xml_bytes
    else:
        json_bytes = json.dumps(problem_body).encode("utf-8")
        media_type = "application/problem+json"
        content = json_bytes

    if request.method == "HEAD":
        headers["Content-Length"] = str(len(content))
        content = b""

    return Response(
        content=content,
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )
