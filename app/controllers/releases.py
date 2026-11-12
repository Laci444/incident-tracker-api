from typing import Any, cast

from litestar import Controller, Request, Response, delete, post, route
from litestar.di import Provide

from app.core.enums import ApiPath, HttpMethod, ReleaseEnvironment, RouteName
from app.core.hypermedia import build_options_response
from app.core.openapi import (
    CREATE_RESPONSES,
    DELETE_RESPONSES,
    OPTIONS_RESPONSES,
    PUBLIC_ITEM_RESPONSES,
    UPDATE_RESPONSES,
    build_mutation_headers,
    build_options_headers,
    build_read_headers,
    merge_patch_openapi_extra,
)
from app.schemas.common import PageLimit, PageOffset, PositiveId, decode_merge_patch
from app.schemas.release import (
    ReleaseCollectionResponseDTO,
    ReleaseCreate,
    ReleasePatch,
    ReleaseResponseDTO,
)
from app.security.guards import require_writer
from app.services.releases import ReleaseService


async def provide_release_patch_changes(request: Request) -> dict[str, Any]:
    return decode_merge_patch(await request.body(), ReleasePatch)


class ReleaseController(Controller):
    path = ""
    tags = ["3. Releases"]

    @route(
        path=ApiPath.SERVICE_RELEASES.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.SERVICE_RELEASES_LIST.versioned(),
        status_code=200,
        summary="List Releases for a specific Service",
        response_headers=build_read_headers(include_last_modified=False),
        responses=PUBLIC_ITEM_RESPONSES,
    )
    async def list_service_releases(
        self,
        release_service: ReleaseService,
        service_id: PositiveId,
        limit: PageLimit = 10,
        offset: PageOffset = 0,
    ) -> ReleaseCollectionResponseDTO:
        page = await release_service.list_service_releases(
            service_id, limit=limit, offset=offset
        )
        return cast(ReleaseCollectionResponseDTO, page)

    @post(
        path=ApiPath.SERVICE_RELEASES.value,
        name=RouteName.SERVICE_RELEASES_CREATE.versioned(),
        status_code=201,
        guards=[require_writer],
        summary="Create a new Release for a Service",
        response_headers=build_mutation_headers(is_created=True),
        responses=CREATE_RESPONSES,
    )
    async def create_service_release(
        self,
        request: Request,
        release_service: ReleaseService,
        service_id: PositiveId,
        data: ReleaseCreate,
    ) -> ReleaseResponseDTO:
        release = await release_service.create_release(service_id, data, request.user)
        return cast(ReleaseResponseDTO, release)

    @route(
        path=ApiPath.SERVICE_RELEASES.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.SERVICE_RELEASES_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for Service Releases Collection",
        response_headers=build_options_headers(),
        responses=OPTIONS_RESPONSES,
    )
    async def options_service_releases(self, service_id: PositiveId) -> Response:
        return build_options_response(
            [HttpMethod.GET, HttpMethod.HEAD, HttpMethod.POST, HttpMethod.OPTIONS]
        )

    @route(
        path=ApiPath.RELEASE_ITEM.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.RELEASE_DETAIL.versioned(),
        status_code=200,
        summary="Get a single Release by ID",
        response_headers=build_read_headers(include_last_modified=True),
        responses=PUBLIC_ITEM_RESPONSES,
    )
    async def get_release(
        self,
        release_service: ReleaseService,
        release_id: PositiveId,
    ) -> ReleaseResponseDTO:
        release = await release_service.get_release(release_id)
        return cast(ReleaseResponseDTO, release)

    @route(
        path=ApiPath.RELEASE_ITEM.value,
        http_method=[HttpMethod.PATCH],
        name=RouteName.RELEASE_PATCH.versioned(),
        status_code=200,
        guards=[require_writer],
        dependencies={"patch_changes": Provide(provide_release_patch_changes)},
        summary="Partially update a Release (RFC 7396 JSON Merge Patch)",
        response_headers=build_mutation_headers(),
        responses=UPDATE_RESPONSES,
        openapi_extra=merge_patch_openapi_extra(
            {"environment": ReleaseEnvironment.PRODUCTION.value, "release_notes": None}
        ),
    )
    async def patch_release(
        self,
        request: Request,
        release_service: ReleaseService,
        release_id: PositiveId,
        patch_changes: dict[str, Any],
    ) -> ReleaseResponseDTO:
        release = await release_service.patch_release(
            release_id, patch_changes, request.scope.get("user")
        )
        return cast(ReleaseResponseDTO, release)

    @delete(
        path=ApiPath.RELEASE_ITEM.value,
        name=RouteName.RELEASE_DELETE.versioned(),
        status_code=204,
        guards=[require_writer],
        summary="Delete a Release (Owner or Admin)",
        responses=DELETE_RESPONSES,
    )
    async def delete_release(
        self,
        request: Request,
        release_service: ReleaseService,
        release_id: PositiveId,
    ) -> None:
        await release_service.delete_release(release_id, request.scope.get("user"))

    @route(
        path=ApiPath.RELEASE_ITEM.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.RELEASE_ITEM_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for a single Release",
        response_headers=build_options_headers(supports_patch=True),
        responses=OPTIONS_RESPONSES,
    )
    async def options_release_item(self, release_id: PositiveId) -> Response:
        return build_options_response(
            [
                HttpMethod.GET,
                HttpMethod.HEAD,
                HttpMethod.PATCH,
                HttpMethod.DELETE,
                HttpMethod.OPTIONS,
            ],
            supports_merge_patch=True,
        )
