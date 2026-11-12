from typing import cast

from litestar import Controller, Response, delete, post, put, route

from app.core.enums import ApiPath, HttpMethod, RouteName, ServiceTier
from app.core.hypermedia import build_options_response
from app.core.openapi import (
    CREATE_RESPONSES,
    DELETE_RESPONSES,
    OPTIONS_RESPONSES,
    PUBLIC_COLLECTION_RESPONSES,
    PUBLIC_ITEM_RESPONSES,
    UPDATE_RESPONSES,
    build_mutation_headers,
    build_options_headers,
    build_read_headers,
)
from app.schemas.common import MergePatchBody, PageLimit, PageOffset, PositiveId
from app.schemas.service import (
    ServiceCollectionResponseDTO,
    ServiceCreate,
    ServicePatch,
    ServiceResponseDTO,
    ServiceUpdate,
)
from app.security.guards import require_admin, require_writer
from app.services.service_catalog import ServiceCatalogService


class ServiceController(Controller):
    path = ""
    tags = ["2. Services"]

    @route(
        path=ApiPath.SERVICES.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.SERVICES_LIST.versioned(),
        status_code=200,
        summary="List Services (with pagination & filtering)",
        response_headers=build_read_headers(include_last_modified=False),
        responses=PUBLIC_COLLECTION_RESPONSES,
    )
    async def list_services(
        self,
        service_catalog: ServiceCatalogService,
        tier: ServiceTier | None = None,
        is_active: bool | None = None,
        limit: PageLimit = 10,
        offset: PageOffset = 0,
    ) -> ServiceCollectionResponseDTO:
        page = await service_catalog.list_services(
            tier=tier, is_active=is_active, limit=limit, offset=offset
        )
        return cast(ServiceCollectionResponseDTO, page)

    @post(
        path=ApiPath.SERVICES.value,
        name=RouteName.SERVICES_CREATE.versioned(),
        status_code=201,
        guards=[require_writer],
        summary="Create a new Service",
        response_headers=build_mutation_headers(is_created=True),
        responses=CREATE_RESPONSES,
    )
    async def create_service(
        self,
        service_catalog: ServiceCatalogService,
        data: ServiceCreate,
    ) -> ServiceResponseDTO:
        service = await service_catalog.create_service(data)
        return cast(ServiceResponseDTO, service)

    @route(
        path=ApiPath.SERVICES.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.SERVICES_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for Services Collection",
        response_headers=build_options_headers(),
        responses=OPTIONS_RESPONSES,
    )
    async def options_services_collection(self) -> Response:
        return build_options_response(
            [HttpMethod.GET, HttpMethod.HEAD, HttpMethod.POST, HttpMethod.OPTIONS]
        )

    @route(
        path=ApiPath.SERVICE_ITEM.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.SERVICE_DETAIL.versioned(),
        status_code=200,
        summary="Get a single Service by ID",
        response_headers=build_read_headers(include_last_modified=True),
        responses=PUBLIC_ITEM_RESPONSES,
    )
    async def get_service(
        self,
        service_catalog: ServiceCatalogService,
        service_id: PositiveId,
    ) -> ServiceResponseDTO:
        service = await service_catalog.get_service(service_id)
        return cast(ServiceResponseDTO, service)

    @put(
        path=ApiPath.SERVICE_ITEM.value,
        name=RouteName.SERVICE_REPLACE.versioned(),
        status_code=200,
        guards=[require_writer],
        summary="Replace a Service (Full Update)",
        response_headers=build_mutation_headers(),
        responses=UPDATE_RESPONSES,
    )
    async def replace_service(
        self,
        service_catalog: ServiceCatalogService,
        service_id: PositiveId,
        data: ServiceUpdate,
    ) -> ServiceResponseDTO:
        service = await service_catalog.replace_service(service_id, data)
        return cast(ServiceResponseDTO, service)

    @route(
        path=ApiPath.SERVICE_ITEM.value,
        http_method=[HttpMethod.PATCH],
        name=RouteName.SERVICE_PATCH.versioned(),
        status_code=200,
        guards=[require_writer],
        summary="Partially update a Service (RFC 7396 JSON Merge Patch)",
        response_headers=build_mutation_headers(),
        responses=UPDATE_RESPONSES,
    )
    async def patch_service(
        self,
        service_catalog: ServiceCatalogService,
        service_id: PositiveId,
        data: MergePatchBody[ServicePatch],
    ) -> ServiceResponseDTO:
        service = await service_catalog.patch_service(
            service_id, data.extract_changes()
        )
        return cast(ServiceResponseDTO, service)

    @delete(
        path=ApiPath.SERVICE_ITEM.value,
        name=RouteName.SERVICE_DELETE.versioned(),
        status_code=204,
        guards=[require_admin],
        summary="Delete a Service (Admin only)",
        responses=DELETE_RESPONSES,
    )
    async def delete_service(
        self,
        service_catalog: ServiceCatalogService,
        service_id: PositiveId,
    ) -> None:
        await service_catalog.delete_service(service_id)

    @route(
        path=ApiPath.SERVICE_ITEM.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.SERVICE_ITEM_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for a single Service",
        response_headers=build_options_headers(supports_patch=True),
        responses=OPTIONS_RESPONSES,
    )
    async def options_service_item(self, service_id: PositiveId) -> Response:
        return build_options_response(
            [
                HttpMethod.GET,
                HttpMethod.HEAD,
                HttpMethod.PUT,
                HttpMethod.PATCH,
                HttpMethod.DELETE,
                HttpMethod.OPTIONS,
            ],
            supports_merge_patch=True,
        )
