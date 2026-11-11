from typing import Any

from litestar import Controller, Request, Response, route

from app.core.caching import (
    build_cache_headers,
    compute_payload_etag,
    evaluate_conditional_get,
)
from app.core.hypermedia import (
    build_options_response,
    format_rfc8288_link_header,
    hal_link,
)
from app.core.renderers import render_resource_response
from app.security.auth import AuthenticatedUser
from app.security.guards import require_authenticated


class RootController(Controller):
    path = "/api"
    tags = ["1. Discovery & Profile"]

    @route(
        path="",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="API Entry Point (HATEOAS Root)",
    )
    async def get_entry_point(self, request: Request) -> Response:
        user: AuthenticatedUser | None = request.scope.get("user")
        links: dict[str, Any] = {
            "self": hal_link("/api", title="API Entry Point"),
            "services": hal_link("/api/services", title="Cloud Services Catalog"),
            "incidents": hal_link("/api/incidents", title="Global Incident Tracker"),
            "me": hal_link("/api/me", title="Current Authenticated User Profile"),
            "describedby": hal_link(
                "/schema/openapi.json", title="OpenAPI 3.1 Specification"
            ),
            "help": hal_link("/schema/swagger", title="Interactive Swagger UI"),
        }

        payload = {
            "api_name": "Cloud-Native Incident & Release Management API",
            "version": "1.0.0",
            "rmm_level": 3,
            "authenticated_as": user.username if user else None,
            "_links": links,
        }

        etag = compute_payload_etag(payload)
        cond_response = evaluate_conditional_get(
            request, etag=etag, is_private=user is not None
        )
        if cond_response is not None:
            return cond_response

        headers = build_cache_headers(
            etag=etag, max_age=60, is_private=user is not None
        )
        headers["Link"] = format_rfc8288_link_header(links)
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="api"
        )

    @route(
        path="",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for API Entry Point",
    )
    async def options_entry_point(self) -> Response:
        return build_options_response(["GET", "HEAD", "OPTIONS"])

    @route(
        path="/me",
        http_method=["GET", "HEAD"],
        status_code=200,
        guards=[require_authenticated],
        summary="Current Authenticated User Profile",
    )
    async def get_current_user(self, request: Request) -> Response:
        user: AuthenticatedUser = request.user
        permissions_map = {
            "admin": ["read", "create", "update_any", "delete_any"],
            "developer": ["read", "create", "update_own", "delete_own"],
            "viewer": ["read"],
        }

        links: dict[str, Any] = {
            "self": hal_link("/api/me", title=user.display_name),
            "up": hal_link("/api", title="API Entry Point"),
            "services": hal_link("/api/services", title="Browse Services"),
            "related": hal_link(
                f"/api/incidents?reported_by={user.username}",
                title=f"Incidents Reported by {user.username}",
            ),
            "describedby": hal_link(
                "/schema/openapi.json", title="OpenAPI Specification"
            ),
        }

        payload = {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "permissions": permissions_map.get(user.role, ["read"]),
            "_links": links,
        }

        etag = compute_payload_etag(payload)
        cond_response = evaluate_conditional_get(request, etag=etag, is_private=True)
        if cond_response is not None:
            return cond_response

        headers = build_cache_headers(etag=etag, max_age=60, is_private=True)
        headers["Link"] = format_rfc8288_link_header(links)
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="profile"
        )

    @route(
        path="/me",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for User Profile",
    )
    async def options_current_user(self) -> Response:
        return build_options_response(["GET", "HEAD", "OPTIONS"])
