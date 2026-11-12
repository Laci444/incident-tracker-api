from typing import Any

import msgspec
from litestar.datastructures import ResponseHeader
from litestar.openapi.datastructures import ResponseSpec

from app.core.enums import HttpHeader, MediaType, ProblemTypeUri


class HALLinkDTO(msgspec.Struct, kw_only=True):
    """OpenAPI schema model for a single HAL hypermedia link."""

    href: str
    title: str | None = None
    method: str | None = None
    type: str | None = None


class ProblemDetailsDTO(msgspec.Struct, kw_only=True):
    """OpenAPI schema model for RFC 9457 Problem Details error responses."""

    type: str = ProblemTypeUri.BAD_REQUEST
    title: str
    status: int
    detail: str
    instance: str
    errors: Any | None = None


HEADER_CSP = ResponseHeader(
    name=HttpHeader.CONTENT_SECURITY_POLICY,
    value="default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    description="Strict Content-Security-Policy header enforced on all API responses.",
    documentation_only=True,
)

HEADER_CACHE_CONTROL = ResponseHeader(
    name=HttpHeader.CACHE_CONTROL,
    value="public, max-age=60, must-revalidate",
    description="HTTP caching directive for client and proxy caches.",
    documentation_only=True,
)

HEADER_ETAG = ResponseHeader(
    name=HttpHeader.ETAG,
    value='"a1b2c3d4e5f60718"',
    description="Strong entity tag for conditional GET (304) and optimistic locking (412).",
    documentation_only=True,
)

HEADER_LAST_MODIFIED = ResponseHeader(
    name=HttpHeader.LAST_MODIFIED,
    value="Tue, 10 Nov 2026 12:00:00 GMT",
    description="Last modification timestamp in RFC 9110 IMF-fixdate format.",
    documentation_only=True,
)

HEADER_LINK = ResponseHeader(
    name=HttpHeader.LINK,
    value='</api/v1/services>; rel="collection", </schema/openapi.json>; rel="describedby"',
    description="RFC 8288 Web Linking header containing IANA link relations.",
    documentation_only=True,
)

HEADER_LOCATION = ResponseHeader(
    name=HttpHeader.LOCATION,
    value="/api/v1/services/1",
    description="Canonical URI of the newly created resource (201 Created).",
    documentation_only=True,
)

HEADER_VARY = ResponseHeader(
    name=HttpHeader.VARY,
    value="Accept, Authorization",
    description="Indicates headers that influence content negotiation and representation.",
    documentation_only=True,
)

HEADER_ALLOW = ResponseHeader(
    name=HttpHeader.ALLOW,
    value="GET, HEAD, PUT, PATCH, DELETE, OPTIONS",
    description="HTTP methods supported by the target resource.",
    documentation_only=True,
)

HEADER_ACCEPT_PATCH = ResponseHeader(
    name=HttpHeader.ACCEPT_PATCH,
    value=MediaType.MERGE_PATCH_JSON,
    description="Advertises support for RFC 7396 JSON Merge Patch.",
    documentation_only=True,
)


def build_read_headers(*, include_last_modified: bool = True) -> list[ResponseHeader]:
    headers = [HEADER_CACHE_CONTROL, HEADER_ETAG, HEADER_LINK, HEADER_VARY, HEADER_CSP]
    if include_last_modified:
        headers.append(HEADER_LAST_MODIFIED)
    return headers


def build_mutation_headers(*, is_created: bool = False) -> list[ResponseHeader]:
    headers = [
        HEADER_CACHE_CONTROL,
        HEADER_ETAG,
        HEADER_LAST_MODIFIED,
        HEADER_LINK,
        HEADER_VARY,
        HEADER_CSP,
    ]
    if is_created:
        headers.append(HEADER_LOCATION)
    return headers


def build_options_headers(*, supports_patch: bool = False) -> list[ResponseHeader]:
    headers = [HEADER_ALLOW, HEADER_CACHE_CONTROL, HEADER_CSP]
    if supports_patch:
        headers.append(HEADER_ACCEPT_PATCH)
    return headers


_ERROR_CATALOG: dict[int, str] = {
    304: "Not Modified - Resource representation has not changed since ETag / Last-Modified (headers: ETag, Cache-Control, CSP).",
    400: "Bad Request - Malformed JSON syntax or empty payload (RFC 9457 Problem Details).",
    401: "Unauthorized - Missing or invalid HTTP Basic credentials; includes WWW-Authenticate header (RFC 9457 Problem Details).",
    403: "Forbidden - Authenticated user lacks role or ownership permissions (RFC 9457 Problem Details).",
    404: "Not Found - Target resource does not exist (RFC 9457 Problem Details).",
    405: "Method Not Allowed - HTTP method not supported by this resource; includes Allow header (RFC 9457 Problem Details).",
    406: "Not Acceptable - Requested Accept media type is not supported (RFC 9457 Problem Details).",
    409: "Conflict - Resource state or uniqueness constraint conflict (RFC 9457 Problem Details).",
    412: "Precondition Failed - If-Match ETag header did not match current state; includes current ETag header (RFC 9457 Problem Details).",
    415: "Unsupported Media Type - Invalid Content-Type header; includes Accept-Patch header on PATCH (RFC 9457 Problem Details).",
    422: "Unprocessable Content - Domain or schema validation failure (RFC 9457 Problem Details).",
}


def build_error_responses(*status_codes: int) -> dict[int, ResponseSpec]:
    """Builds OpenAPI ResponseSpec entries using RFC 9457 ProblemDetailsDTO."""
    specs: dict[int, ResponseSpec] = {}
    for code in status_codes:
        description = _ERROR_CATALOG[code]
        if code == 304:
            specs[code] = ResponseSpec(
                data_container=None,
                description=description,
                generate_examples=False,
            )
        else:
            specs[code] = ResponseSpec(
                data_container=ProblemDetailsDTO,
                media_type=MediaType.PROBLEM_JSON,
                description=description,
                generate_examples=False,
            )
    return specs


PUBLIC_COLLECTION_RESPONSES = build_error_responses(304, 405, 406, 422)
PUBLIC_ITEM_RESPONSES = build_error_responses(304, 404, 405, 406)
AUTH_READ_RESPONSES = build_error_responses(304, 401, 405, 406)
CREATE_RESPONSES = build_error_responses(400, 401, 403, 404, 405, 406, 409, 415, 422)
UPDATE_RESPONSES = build_error_responses(
    400, 401, 403, 404, 405, 406, 409, 412, 415, 422
)
DELETE_RESPONSES = build_error_responses(401, 403, 404, 405, 412)
OPTIONS_RESPONSES = build_error_responses(405)
