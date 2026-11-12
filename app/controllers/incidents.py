from typing import Any, cast

from litestar import Controller, Request, Response, delete, post, put, route
from litestar.di import Provide

from app.core.enums import (
    ApiPath,
    HttpMethod,
    IncidentSeverity,
    IncidentStatus,
    RouteName,
)
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
    merge_patch_openapi_extra,
)
from app.schemas.common import PageLimit, PageOffset, PositiveId, decode_merge_patch
from app.schemas.incident import (
    IncidentCollectionResponseDTO,
    IncidentCreate,
    IncidentPatch,
    IncidentResponseDTO,
    IncidentUpdate,
)
from app.security.guards import require_writer
from app.services.incidents import IncidentService


async def provide_incident_patch_changes(request: Request) -> dict[str, Any]:
    return decode_merge_patch(await request.body(), IncidentPatch)


class IncidentController(Controller):
    path = ""
    tags = ["4. Incidents"]

    @route(
        path=ApiPath.INCIDENTS.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.INCIDENTS_LIST.versioned(),
        status_code=200,
        summary="List Incidents (with filtering & pagination)",
        response_headers=build_read_headers(include_last_modified=False),
        responses=PUBLIC_COLLECTION_RESPONSES,
    )
    async def list_incidents(
        self,
        incident_service: IncidentService,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
        service_id: PositiveId | None = None,
        reported_by: str | None = None,
        limit: PageLimit = 10,
        offset: PageOffset = 0,
    ) -> IncidentCollectionResponseDTO:
        page = await incident_service.list_incidents(
            status=status,
            severity=severity,
            service_id=service_id,
            reported_by=reported_by,
            limit=limit,
            offset=offset,
        )
        return cast(IncidentCollectionResponseDTO, page)

    @post(
        path=ApiPath.INCIDENTS.value,
        name=RouteName.INCIDENTS_CREATE.versioned(),
        status_code=201,
        guards=[require_writer],
        summary="Report a new Incident",
        response_headers=build_mutation_headers(is_created=True),
        responses=CREATE_RESPONSES,
    )
    async def create_incident(
        self,
        request: Request,
        incident_service: IncidentService,
        data: IncidentCreate,
    ) -> IncidentResponseDTO:
        incident = await incident_service.create_incident(data, request.user)
        return cast(IncidentResponseDTO, incident)

    @route(
        path=ApiPath.INCIDENTS.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.INCIDENTS_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for Incidents Collection",
        response_headers=build_options_headers(),
        responses=OPTIONS_RESPONSES,
    )
    async def options_incidents_collection(self) -> Response:
        return build_options_response(
            [HttpMethod.GET, HttpMethod.HEAD, HttpMethod.POST, HttpMethod.OPTIONS]
        )

    @route(
        path=ApiPath.INCIDENT_ITEM.value,
        http_method=[HttpMethod.GET, HttpMethod.HEAD],
        name=RouteName.INCIDENT_DETAIL.versioned(),
        status_code=200,
        summary="Get a single Incident by ID",
        response_headers=build_read_headers(include_last_modified=True),
        responses=PUBLIC_ITEM_RESPONSES,
    )
    async def get_incident(
        self,
        incident_service: IncidentService,
        incident_id: PositiveId,
    ) -> IncidentResponseDTO:
        incident = await incident_service.get_incident(incident_id)
        return cast(IncidentResponseDTO, incident)

    @put(
        path=ApiPath.INCIDENT_ITEM.value,
        name=RouteName.INCIDENT_REPLACE.versioned(),
        status_code=200,
        guards=[require_writer],
        summary="Replace an Incident (Full Update)",
        response_headers=build_mutation_headers(),
        responses=UPDATE_RESPONSES,
    )
    async def replace_incident(
        self,
        request: Request,
        incident_service: IncidentService,
        incident_id: PositiveId,
        data: IncidentUpdate,
    ) -> IncidentResponseDTO:
        incident = await incident_service.replace_incident(
            incident_id, data, request.scope.get("user")
        )
        return cast(IncidentResponseDTO, incident)

    @route(
        path=ApiPath.INCIDENT_ITEM.value,
        http_method=[HttpMethod.PATCH],
        name=RouteName.INCIDENT_PATCH.versioned(),
        status_code=200,
        guards=[require_writer],
        dependencies={"patch_changes": Provide(provide_incident_patch_changes)},
        summary="Partially update an Incident (RFC 7396 JSON Merge Patch)",
        response_headers=build_mutation_headers(),
        responses=UPDATE_RESPONSES,
        openapi_extra=merge_patch_openapi_extra(
            {
                "status": IncidentStatus.RESOLVED.value,
                "resolution_notes": "Root cause fixed and verified.",
                "release_id": None,
            }
        ),
    )
    async def patch_incident(
        self,
        request: Request,
        incident_service: IncidentService,
        incident_id: PositiveId,
        patch_changes: dict[str, Any],
    ) -> IncidentResponseDTO:
        incident = await incident_service.patch_incident(
            incident_id, patch_changes, request.scope.get("user")
        )
        return cast(IncidentResponseDTO, incident)

    @delete(
        path=ApiPath.INCIDENT_ITEM.value,
        name=RouteName.INCIDENT_DELETE.versioned(),
        status_code=204,
        guards=[require_writer],
        summary="Delete an Incident (Owner or Admin)",
        responses=DELETE_RESPONSES,
    )
    async def delete_incident(
        self,
        request: Request,
        incident_service: IncidentService,
        incident_id: PositiveId,
    ) -> None:
        await incident_service.delete_incident(incident_id, request.scope.get("user"))

    @route(
        path=ApiPath.INCIDENT_ITEM.value,
        http_method=[HttpMethod.OPTIONS],
        name=RouteName.INCIDENT_ITEM_OPTIONS.versioned(),
        status_code=204,
        summary="OPTIONS for a single Incident",
        response_headers=build_options_headers(supports_patch=True),
        responses=OPTIONS_RESPONSES,
    )
    async def options_incident_item(self, incident_id: PositiveId) -> Response:
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
