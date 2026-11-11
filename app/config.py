from pathlib import Path

from litestar.config.cors import CORSConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.openapi.spec import (
    Components,
    Contact,
    OpenAPIHeader,
    OpenAPIMediaType,
    OpenAPIResponse,
    OpenAPIType,
    Schema,
    SecurityScheme,
)

BASE_DIR = Path(__file__).resolve().parent.parent / 'data'
DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR / 'incident_tracker.db'}"

API_CSP_HEADER = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

SWAGGER_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "frame-ancestors 'none'"
)

cors_config = CORSConfig(
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "If-Match",
        "If-None-Match",
        "If-Modified-Since",
    ],
    expose_headers=[
        "ETag",
        "Last-Modified",
        "Cache-Control",
        "Location",
        "Link",
        "Allow",
        "Accept-Patch",
        "Content-Security-Policy",
        "WWW-Authenticate",
    ],
    allow_credentials=True,
    max_age=3600,
)

problem_details_schema = Schema(
    title="ProblemDetails",
    description="RFC 9457 Problem Details for HTTP APIs",
    type=OpenAPIType.OBJECT,
    required=["type", "title", "status", "detail", "instance"],
    properties={
        "type": Schema(type=OpenAPIType.STRING, example="urn:problem-type:not-found"),
        "title": Schema(type=OpenAPIType.STRING, example="Resource Not Found"),
        "status": Schema(type=OpenAPIType.INTEGER, example=404),
        "detail": Schema(type=OpenAPIType.STRING, example="Service with id=99999 does not exist."),
        "instance": Schema(type=OpenAPIType.STRING, example="/api/services/99999"),
    },
)

hal_link_schema = Schema(
    title="HALLink",
    type=OpenAPIType.OBJECT,
    required=["href"],
    properties={
        "href": Schema(type=OpenAPIType.STRING, example="/api/services/1"),
        "title": Schema(type=OpenAPIType.STRING, example="Identity & Auth Gateway"),
        "method": Schema(type=OpenAPIType.STRING, example="GET"),
    },
)

problem_response = OpenAPIResponse(
    description="RFC 9457 Problem Details error response (JSON or XML)",
    content={
        "application/problem+json": OpenAPIMediaType(schema=problem_details_schema),
        "application/problem+xml": OpenAPIMediaType(schema=problem_details_schema),
    },
    headers={
        "Cache-Control": OpenAPIHeader(
            description="Always set to no-store on error responses",
            schema=Schema(type=OpenAPIType.STRING, example="no-store"),
        )
    },
)

openapi_config = OpenAPIConfig(
    title="Cloud-Native Incident & Release Management API",
    version="1.0.0",
    description=(
        "A Level 3 RESTful Web API implementing HATEOAS (HAL + Link headers), "
        "RFC 9457 Problem Details, RFC 7396 JSON Merge Patch, HTTP caching (ETag / Last-Modified), "
        "and stateless HTTP Basic Authentication.\n\n"
        "### Supported Error Status Codes (all formatted as RFC 9457 Problem Details)\n"
        "- **400 Bad Request**: Malformed JSON body\n"
        "- **401 Unauthorized**: Missing or invalid HTTP Basic credentials (includes `WWW-Authenticate` header)\n"
        "- **403 Forbidden**: Authenticated user lacks required role or resource ownership\n"
        "- **404 Not Found**: Target resource URI does not exist\n"
        "- **405 Method Not Allowed**: HTTP method not supported on resource (includes `Allow` header)\n"
        "- **406 Not Acceptable**: Requested `Accept` media type is not supported\n"
        "- **409 Conflict**: Resource uniqueness constraint violation\n"
        "- **412 Precondition Failed**: `If-Match` ETag precondition failed (optimistic concurrency control)\n"
        "- **415 Unsupported Media Type**: Invalid `Content-Type` (e.g., `PATCH` without `application/merge-patch+json`)\n"
        "- **422 Unprocessable Content**: Semantic or schema validation failure"
    ),
    contact=Contact(name="API Architecture Team"),
    path="/schema",
    render_plugins=[SwaggerRenderPlugin(path="/swagger")],
    components=Components(
        schemas={
            "ProblemDetails": problem_details_schema,
            "HALLink": hal_link_schema,
        },
        responses={
            "ProblemError": problem_response,
        },
        security_schemes={
            "BasicAuth": SecurityScheme(
                type="http",
                scheme="basic",
                description="Stateless HTTP Basic Authentication (admin, dev_alice, viewer_bob)",
            )
        },
    ),
    security=[{"BasicAuth": []}],
)
