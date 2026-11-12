import json
from collections.abc import Sequence
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

from app.core.enums import HttpHeader, HttpMethod, MediaType, ProblemTypeUri

AUTH_REALM_HEADER_VALUE = 'Basic realm="IncidentReleaseAPI", charset="UTF-8"'


class ProblemException(Exception):
    """Base exception for RFC 9457 Problem Details responses."""

    status_code: int = 500
    title: str = "Internal Server Error"
    type_uri: str = ProblemTypeUri.INTERNAL_ERROR

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        title: str | None = None,
        type_uri: str | None = None,
        headers: dict[str, str] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        if status_code is not None:
            self.status_code = status_code
        if title is not None:
            self.title = title
        if type_uri is not None:
            self.type_uri = type_uri
        self.detail = detail
        self.headers: dict[str, str] = dict(headers or {})
        self.extensions: dict[str, Any] = dict(extensions or {})


class BadRequestError(ProblemException):
    status_code = 400
    title = "Bad Request"
    type_uri = ProblemTypeUri.BAD_REQUEST


class UnauthorizedError(ProblemException):
    status_code = 401
    title = "Unauthorized"
    type_uri = ProblemTypeUri.UNAUTHORIZED

    def __init__(
        self,
        detail: str = "Valid HTTP Basic Authentication credentials are required.",
    ) -> None:
        super().__init__(
            detail,
            headers={HttpHeader.WWW_AUTHENTICATE: AUTH_REALM_HEADER_VALUE},
        )


class ForbiddenError(ProblemException):
    status_code = 403
    title = "Forbidden"
    type_uri = ProblemTypeUri.FORBIDDEN


class ResourceNotFoundError(ProblemException):
    status_code = 404
    title = "Resource Not Found"
    type_uri = ProblemTypeUri.NOT_FOUND

    def __init__(self, resource_name: str, identifier: Any) -> None:
        super().__init__(
            f"{resource_name.capitalize()} resource with id='{identifier}' does not exist."
        )


class MethodNotAllowedError(ProblemException):
    status_code = 405
    title = "Method Not Allowed"
    type_uri = ProblemTypeUri.METHOD_NOT_ALLOWED

    def __init__(self, method: str, path: str, allowed_methods: Sequence[str]) -> None:
        allow_header = ", ".join(allowed_methods)
        super().__init__(
            f"HTTP method {method} is not allowed for '{path}'. Allowed: {allow_header}.",
            headers={HttpHeader.ALLOW: allow_header},
        )


class NotAcceptableError(ProblemException):
    status_code = 406
    title = "Not Acceptable"
    type_uri = ProblemTypeUri.NOT_ACCEPTABLE

    def __init__(self, accept_header: str, supported_types: Sequence[str]) -> None:
        supported_list = ", ".join(supported_types)
        super().__init__(
            f"Requested media type '{accept_header}' is not supported. Supported: {supported_list}."
        )


class ResourceConflictError(ProblemException):
    status_code = 409
    title = "Conflict"
    type_uri = ProblemTypeUri.CONFLICT


class PreconditionFailedError(ProblemException):
    status_code = 412
    title = "Precondition Failed"
    type_uri = ProblemTypeUri.PRECONDITION_FAILED

    def __init__(self, current_etag: str, provided_if_match: str) -> None:
        super().__init__(
            f"Resource ETag {current_etag} does not match If-Match precondition ({provided_if_match}).",
            headers={HttpHeader.ETAG: current_etag},
        )


class UnsupportedMediaTypeError(ProblemException):
    status_code = 415
    title = "Unsupported Media Type"
    type_uri = ProblemTypeUri.UNSUPPORTED_MEDIA_TYPE

    def __init__(self, detail: str, *, advertise_merge_patch: bool = False) -> None:
        headers = (
            {HttpHeader.ACCEPT_PATCH: MediaType.MERGE_PATCH_JSON}
            if advertise_merge_patch
            else None
        )
        super().__init__(detail, headers=headers)


class ValidationFailedError(ProblemException):
    status_code = 422
    title = "Unprocessable Content"
    type_uri = ProblemTypeUri.VALIDATION_ERROR

    def __init__(self, detail: str, *, errors: Any = None) -> None:
        extensions = {"errors": errors} if errors is not None else None
        super().__init__(detail, extensions=extensions)


def _prefers_xml_problem(request: Request) -> bool:
    accept = request.headers.get(HttpHeader.ACCEPT.lower(), "").lower()
    return MediaType.PROBLEM_XML in accept or (
        MediaType.XML in accept and "json" not in accept
    )


def problem_exception_handler(request: Request, exc: Exception) -> Response:
    status_code = 500
    title = "Internal Server Error"
    detail = "An unexpected error occurred while processing the request."
    type_uri: str = ProblemTypeUri.INTERNAL_ERROR
    headers: dict[str, str] = {HttpHeader.CACHE_CONTROL: "no-store"}
    extensions: dict[str, Any] = {}

    if isinstance(exc, ProblemException):
        status_code = exc.status_code
        title = exc.title
        detail = exc.detail
        type_uri = exc.type_uri
        headers.update(exc.headers)
        extensions.update(exc.extensions)

    elif isinstance(exc, ValidationException):
        status_code = 422
        title = "Unprocessable Content"
        detail = "Request payload or query parameters failed schema validation."
        type_uri = ProblemTypeUri.VALIDATION_ERROR
        extensions["errors"] = exc.extra or exc.detail

    elif isinstance(exc, MethodNotAllowedException):
        status_code = 405
        title = "Method Not Allowed"
        detail = f"HTTP method {request.method} is not allowed for '{request.url.path}'."
        type_uri = ProblemTypeUri.METHOD_NOT_ALLOWED
        if exc.headers:
            headers.update(exc.headers)

    elif isinstance(exc, NotFoundException):
        status_code = 404
        title = "Resource Not Found"
        detail = f"No resource found at URI '{request.url.path}'."
        type_uri = ProblemTypeUri.NOT_FOUND

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

    if status_code == 401 and HttpHeader.WWW_AUTHENTICATE not in headers:
        headers[HttpHeader.WWW_AUTHENTICATE] = AUTH_REALM_HEADER_VALUE

    problem_payload: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        **extensions,
    }

    if _prefers_xml_problem(request):
        content = dicttoxml(problem_payload, custom_root="problem", attr_type=False)
        media_type = MediaType.PROBLEM_XML
    else:
        content = json.dumps(problem_payload).encode("utf-8")
        media_type = MediaType.PROBLEM_JSON

    if request.method == HttpMethod.HEAD:
        headers[HttpHeader.CONTENT_LENGTH] = str(len(content))
        content = b""

    return Response(
        content=content,
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )
