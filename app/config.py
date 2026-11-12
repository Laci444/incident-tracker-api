import os
from pathlib import Path

from litestar.config.cors import CORSConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.openapi.spec import Components, Contact, SecurityScheme

from app.core.enums import ApiPath, HttpHeader, HttpMethod

BASE_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_PATH = BASE_DIR / "incident_tracker.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# Strict CSP for pure API endpoints
API_CSP_HEADER = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

# Relaxed CSP exclusively for /schema/* routes so Swagger UI assets can execute
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
    allow_methods=[m.value for m in HttpMethod],
    allow_headers=[
        HttpHeader.ACCEPT,
        HttpHeader.AUTHORIZATION,
        HttpHeader.CONTENT_TYPE,
        HttpHeader.IF_MATCH,
        HttpHeader.IF_NONE_MATCH,
        HttpHeader.IF_MODIFIED_SINCE,
    ],
    expose_headers=[
        HttpHeader.ETAG,
        HttpHeader.LAST_MODIFIED,
        HttpHeader.CACHE_CONTROL,
        HttpHeader.LOCATION,
        HttpHeader.LINK,
        HttpHeader.ALLOW,
        HttpHeader.ACCEPT_PATCH,
        HttpHeader.CONTENT_SECURITY_POLICY,
        HttpHeader.WWW_AUTHENTICATE,
    ],
    allow_credentials=True,
    max_age=3600,
)

openapi_config = OpenAPIConfig(
    title="Cloud-Native Incident & Release Management API",
    version="1.0.0",
    description=(
        "A versioned, Level 3 RESTful Web API implementing HATEOAS (HAL + RFC 8288 Link headers), "
        "RFC 9457 Problem Details, RFC 7396 JSON Merge Patch, HTTP caching (ETag / Last-Modified / 304 / 412), "
        "content negotiation (HAL+JSON, JSON, XML), and stateless HTTP Basic Authentication."
    ),
    contact=Contact(name="API Architecture Team"),
    path=ApiPath.SCHEMA_ROOT,
    render_plugins=[SwaggerRenderPlugin(path="/swagger")],
    components=Components(
        security_schemes={
            "BasicAuth": SecurityScheme(
                type="http",
                scheme="basic",
                description="Stateless HTTP Basic Authentication (admin, dev_alice, viewer_bob)",
            )
        }
    ),
    security=[{"BasicAuth": []}],
)
