from typing import Any, cast

from litestar import Controller, Request, Response, route

from app.core.enums import (
    ApiPath,
    ApiVersion,
    CollectionName,
    HttpMethod,
    LinkRel,
    ResourceName,
    RouteName,
    UserRole,
)
from app.core.hypermedia import (
    DomainPayload,
    HypermediaAssembler,
    build_options_response,
    hal_link,
)
from app.core.openapi import (
    AUTH_READ_RESPONSES,
    OPTIONS_RESPONSES,
    PUBLIC_COLLECTION_RESPONSES,
    build_options_headers,
    build_read_headers,
)
from app.schemas.common import (
    ApiDiscoveryResponseDTO,
    UserProfileResponseDTO,
    VersionIndexResponseDTO,
)
from app.security.auth import AuthenticatedUser
from app.security.guards import require_authenticated

_ROLE_PERMISSIONS: dict[UserRole, list[str]] = {
    UserRole.ADMIN: ["read", "create", "update_any", "delete_any"],
    UserRole.DEVELOPER: ["read", "create", "update_own", "delete_own"],
    UserRole.VIEWER: ["read"],
}


class DiscoveryController(Controller):
    """Version-agnostic API discovery root (/api)."""

    path = ApiPath.ROOT.value
    tags = ["1. Discovery & Profile"]

    @route(
        path="",
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.API_DISCOVERY.value,
        status_code=200,
        summary="Version-Agnostic API Discovery Entry Point",
        response_headers=build_read_headers(include_last_modified=False),
        responses=PUBLIC_COLLECTION_RESPONSES,
    )
    async def get_discovery_root(self, request: Request) -> ApiDiscoveryResponseDTO:
        assembler = HypermediaAssembler(request, version=ApiVersion.CURRENT)
        links: dict[str, Any] = {
            LinkRel.SELF.value: hal_link(
                assembler.resolve_url(RouteName.API_DISCOVERY),
                title="API Discovery Root",
            ),
            LinkRel.LATEST_VERSION.value: hal_link(
                assembler.resolve_url(RouteName.VERSION_ROOT),
                title=f"API {ApiVersion.CURRENT.value.upper()} Entry Point",
            ),
            CollectionName.SERVICES.value: hal_link(
                assembler.resolve_url(RouteName.SERVICES_LIST),
                title="Cloud Services Catalog",
            ),
            CollectionName.INCIDENTS.value: hal_link(
                assembler.resolve_url(RouteName.INCIDENTS_LIST),
                title="Global Incident Tracker",
            ),
            LinkRel.ABOUT.value: hal_link(
                assembler.resolve_url(RouteName.ME),
                title="Authenticated User Profile",
            ),
            LinkRel.DESCRIBEDBY.value: hal_link(
                ApiPath.OPENAPI_JSON.value,
                title="OpenAPI 3.1 Specification",
            ),
            LinkRel.HELP.value: hal_link(
                ApiPath.SWAGGER_UI.value,
                title="Interactive Swagger UI",
            ),
        }
        payload = DomainPayload(
            data={
                "api_name": "Cloud-Native Incident & Release Management API",
                "current_version": ApiVersion.CURRENT.value,
                "supported_versions": [ApiVersion.V1.value],
                "rmm_level": 3,
            },
            links=links,
            xml_root=ResourceName.API,
            is_private=False,
        )
        return cast(ApiDiscoveryResponseDTO, payload)

    @route(
        path="",
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.API_DISCOVERY_OPTIONS.value,
        status_code=204,
        summary="OPTIONS for API Discovery Entry Point",
        response_headers=build_options_headers(),
        responses=OPTIONS_RESPONSES,
    )
    async def options_discovery_root(self) -> Response:
        return build_options_response(
            [HttpMethod.GET, HttpMethod.HEAD, HttpMethod.OPTIONS]
        )


class VersionRootController(Controller):
    """Versioned entry point (/api/v1) and user profile (/api/v1/me)."""

    path = ""
    tags = ["1. Discovery & Profile"]

    @route(
        path="",
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.VERSION_ROOT.versioned(),
        status_code=200,
        summary="Versioned API Entry Point (v1)",
        response_headers=build_read_headers(include_last_modified=False),
        responses=PUBLIC_COLLECTION_RESPONSES,
    )
    async def get_v1_root(self, request: Request) -> VersionIndexResponseDTO:
        user: AuthenticatedUser | None = request.scope.get("user")
        assembler = HypermediaAssembler(request, version=ApiVersion.V1)
        links: dict[str, Any] = {
            LinkRel.SELF.value: hal_link(
                assembler.resolve_url(RouteName.VERSION_ROOT),
                title="API v1 Entry Point",
            ),
            LinkRel.UP.value: hal_link(
                assembler.resolve_url(RouteName.API_DISCOVERY),
                title="API Discovery Root",
            ),
            CollectionName.SERVICES.value: hal_link(
                assembler.resolve_url(RouteName.SERVICES_LIST),
                title="Cloud Services Catalog",
            ),
            CollectionName.INCIDENTS.value: hal_link(
                assembler.resolve_url(RouteName.INCIDENTS_LIST),
                title="Global Incident Tracker",
            ),
            LinkRel.ABOUT.value: hal_link(
                assembler.resolve_url(RouteName.ME),
                title="Current Authenticated User Profile",
            ),
            LinkRel.DESCRIBEDBY.value: hal_link(
                ApiPath.OPENAPI_JSON.value,
                title="OpenAPI 3.1 Specification",
            ),
            LinkRel.HELP.value: hal_link(
                ApiPath.SWAGGER_UI.value,
                title="Interactive Swagger UI",
            ),
        }
        payload = DomainPayload(
            data={
                "api_name": "Cloud-Native Incident & Release Management API",
                "version": ApiVersion.V1.value,
                "rmm_level": 3,
                "authenticated_as": user.username if user else None,
            },
            links=links,
            xml_root=ResourceName.VERSION_INDEX,
            is_private=user is not None,
        )
        return cast(VersionIndexResponseDTO, payload)

    @route(
        path="",
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.VERSION_ROOT_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for Versioned Entry Point",
        response_headers=build_options_headers(),
        responses=OPTIONS_RESPONSES,
    )
    async def options_v1_root(self) -> Response:
        return build_options_response(
            [HttpMethod.GET, HttpMethod.HEAD, HttpMethod.OPTIONS]
        )

    @route(
        path=ApiPath.ME.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.ME.versioned(),
        status_code=200,
        guards=[require_authenticated],
        summary="Current Authenticated User Profile",
        response_headers=build_read_headers(include_last_modified=False),
        responses=AUTH_READ_RESPONSES,
    )
    async def get_current_user(self, request: Request) -> UserProfileResponseDTO:
        user: AuthenticatedUser = request.user
        assembler = HypermediaAssembler(request, version=ApiVersion.V1)
        incidents_uri = assembler.resolve_url(
            RouteName.INCIDENTS_LIST, reported_by=user.username
        )

        links: dict[str, Any] = {
            LinkRel.SELF.value: hal_link(
                assembler.resolve_url(RouteName.ME),
                title=user.display_name,
            ),
            LinkRel.UP.value: hal_link(
                assembler.resolve_url(RouteName.VERSION_ROOT),
                title="API v1 Entry Point",
            ),
            CollectionName.SERVICES.value: hal_link(
                assembler.resolve_url(RouteName.SERVICES_LIST),
                title="Browse Services",
            ),
            LinkRel.RELATED.value: hal_link(
                incidents_uri,
                title=f"Incidents Reported by {user.username}",
            ),
            LinkRel.DESCRIBEDBY.value: hal_link(
                ApiPath.OPENAPI_JSON.value,
                title="OpenAPI Specification",
            ),
        }
        payload = DomainPayload(
            data={
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "permissions": _ROLE_PERMISSIONS.get(user.role, ["read"]),
            },
            links=links,
            xml_root=ResourceName.PROFILE,
            is_private=True,
        )
        return cast(UserProfileResponseDTO, payload)

    @route(
        path=ApiPath.ME.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.ME_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for User Profile",
        response_headers=build_options_headers(),
        responses=OPTIONS_RESPONSES,
    )
    async def options_current_user(self) -> Response:
        return build_options_response(
            [HttpMethod.GET, HttpMethod.HEAD, HttpMethod.OPTIONS]
        )
