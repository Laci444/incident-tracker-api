from typing import Any

import msgspec
from litestar import Controller, Request, Response, delete, post, put, route
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.releases import _get_release_or_404
from app.controllers.services import _get_service_or_404
from app.core.caching import (
    build_cache_headers,
    compute_payload_etag,
    evaluate_conditional_get,
    verify_if_match,
)
from app.core.exceptions import ProblemException
from app.core.hypermedia import (
    build_options_response,
    format_rfc8288_link_header,
    hal_link,
)
from app.core.renderers import render_resource_response
from app.db.models import IncidentModel, utc_now
from app.schemas.common import merge_patch_openapi_body, parse_merge_patch_body
from app.schemas.incident import (
    IncidentCreate,
    IncidentPatch,
    IncidentUpdate,
    serialize_incident_hal,
    validate_incident_fields,
)
from app.security.auth import AuthenticatedUser
from app.security.guards import ensure_owner_or_admin, require_writer


async def _get_incident_or_404(
    db_session: AsyncSession, incident_id: int
) -> IncidentModel:
    incident = await db_session.get(IncidentModel, incident_id)
    if incident is None:
        raise ProblemException(
            status_code=404,
            title="Resource Not Found",
            detail=f"Incident with id={incident_id} does not exist.",
            type_slug="incident-not-found",
        )
    return incident


async def _validate_service_and_release_relation(
    db_session: AsyncSession, service_id: int, release_id: int | None
) -> None:
    await _get_service_or_404(db_session, service_id)
    if release_id is not None:
        release = await _get_release_or_404(db_session, release_id)
        if release.service_id != service_id:
            raise ProblemException(
                status_code=422,
                title="Unprocessable Content",
                detail=f"Release id={release_id} belongs to service id={release.service_id}, not service id={service_id}.",
                type_slug="release-service-mismatch",
            )


class IncidentController(Controller):
    path = "/api/incidents"
    tags = ["4. Incidents"]

    @route(
        path="",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="List Incidents (with filtering & pagination)",
    )
    async def list_incidents(
        self,
        request: Request,
        db_session: AsyncSession,
        status: str | None = None,
        severity: str | None = None,
        service_id: int | None = None,
        reported_by: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Response:
        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        stmt = select(IncidentModel).order_by(IncidentModel.id.desc())
        count_stmt = select(func.count(IncidentModel.id))

        filters = []
        if status is not None:
            filters.append(IncidentModel.status == status)
        if severity is not None:
            filters.append(IncidentModel.severity == severity)
        if service_id is not None:
            filters.append(IncidentModel.service_id == service_id)
        if reported_by is not None:
            filters.append(IncidentModel.reported_by == reported_by)

        for cond in filters:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total: int = (await db_session.scalar(count_stmt)) or 0
        incidents = list(
            (await db_session.scalars(stmt.limit(limit).offset(offset))).all()
        )

        user: AuthenticatedUser | None = request.scope.get("user")
        embedded = [serialize_incident_hal(inc, user) for inc in incidents]

        links: dict[str, Any] = {
            "self": hal_link(
                f"/api/incidents?limit={limit}&offset={offset}",
                title="Incidents Collection",
            ),
            "up": hal_link("/api", title="API Entry Point"),
            "first": hal_link(
                f"/api/incidents?limit={limit}&offset=0", title="First Page"
            ),
            "item": [
                hal_link(f"/api/incidents/{inc.id}", title=inc.title)
                for inc in incidents
            ],
            "describedby": hal_link(
                "/schema/openapi.json", title="OpenAPI Specification"
            ),
        }
        if offset + limit < total:
            links["next"] = hal_link(
                f"/api/incidents?limit={limit}&offset={offset + limit}",
                title="Next Page",
            )
        if offset > 0:
            links["prev"] = hal_link(
                f"/api/incidents?limit={limit}&offset={max(0, offset - limit)}",
                title="Previous Page",
            )
        if user and user.role in ("admin", "developer"):
            links["create-form"] = hal_link(
                "/api/incidents", title="Report New Incident", method="POST"
            )

        payload = {
            "total": total,
            "count": len(embedded),
            "limit": limit,
            "offset": offset,
            "_links": links,
            "_embedded": {"incidents": embedded},
        }

        etag = compute_payload_etag(payload)
        cond_response = evaluate_conditional_get(request, etag=etag)
        if cond_response is not None:
            return cond_response

        headers = build_cache_headers(etag=etag, max_age=30)
        headers["Link"] = format_rfc8288_link_header(links)
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="incidents"
        )

    @post(
        path="",
        status_code=201,
        guards=[require_writer],
        summary="Report a new Incident",
    )
    async def create_incident(
        self,
        request: Request,
        db_session: AsyncSession,
        data: IncidentCreate,
    ) -> Response:
        validate_incident_fields(data.severity, data.status)
        await _validate_service_and_release_relation(
            db_session, data.service_id, data.release_id
        )

        user: AuthenticatedUser = request.user
        incident = IncidentModel(
            service_id=data.service_id,
            release_id=data.release_id,
            title=data.title.strip(),
            summary=data.summary.strip(),
            severity=data.severity,
            status=data.status,
            resolution_notes=data.resolution_notes,
            reported_by=user.username,
        )
        db_session.add(incident)
        await db_session.commit()
        await db_session.refresh(incident)

        payload = serialize_incident_hal(incident, user)
        etag = incident.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=incident.updated_at)
        headers["Location"] = f"/api/incidents/{incident.id}"
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=201, headers=headers, xml_root="incident"
        )

    @route(
        path="",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for Incidents Collection",
    )
    async def options_incidents_collection(self) -> Response:
        return build_options_response(["GET", "HEAD", "POST", "OPTIONS"])

    @route(
        path="/{incident_id:int}",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="Get a single Incident by ID",
    )
    async def get_incident(
        self,
        request: Request,
        db_session: AsyncSession,
        incident_id: int,
    ) -> Response:
        incident = await _get_incident_or_404(db_session, incident_id)
        etag = incident.compute_etag()

        cond_response = evaluate_conditional_get(
            request, etag=etag, last_modified=incident.updated_at
        )
        if cond_response is not None:
            return cond_response

        user: AuthenticatedUser | None = request.scope.get("user")
        payload = serialize_incident_hal(incident, user)
        headers = build_cache_headers(
            etag=etag, last_modified=incident.updated_at, max_age=60
        )
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="incident"
        )

    @put(
        path="/{incident_id:int}",
        status_code=200,
        guards=[require_writer],
        summary="Replace an Incident (Full Update)",
    )
    async def replace_incident(
        self,
        request: Request,
        db_session: AsyncSession,
        incident_id: int,
        data: IncidentUpdate,
    ) -> Response:
        incident = await _get_incident_or_404(db_session, incident_id)
        user: AuthenticatedUser | None = request.scope.get("user")
        ensure_owner_or_admin(user, incident.reported_by)
        verify_if_match(request, incident.compute_etag())

        validate_incident_fields(data.severity, data.status)
        await _validate_service_and_release_relation(
            db_session, data.service_id, data.release_id
        )

        incident.service_id = data.service_id
        incident.release_id = data.release_id
        incident.title = data.title.strip()
        incident.summary = data.summary.strip()
        incident.severity = data.severity
        incident.status = data.status
        incident.resolution_notes = data.resolution_notes
        incident.updated_at = utc_now()

        await db_session.commit()
        await db_session.refresh(incident)

        payload = serialize_incident_hal(incident, user)
        etag = incident.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=incident.updated_at)
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="incident"
        )

    @route(
        path="/{incident_id:int}",
        http_method=["PATCH"],
        status_code=200,
        guards=[require_writer],
        summary="Partially update an Incident (RFC 7396 JSON Merge Patch)",
        openapi_extra=merge_patch_openapi_body(
            {
                "status": "resolved",
                "resolution_notes": "Root cause fixed and verified.",
                "release_id": None,
            }
        ),
    )
    async def patch_incident(
        self,
        request: Request,
        db_session: AsyncSession,
        incident_id: int,
    ) -> Response:
        incident = await _get_incident_or_404(db_session, incident_id)
        user: AuthenticatedUser | None = request.scope.get("user")
        ensure_owner_or_admin(user, incident.reported_by)
        verify_if_match(request, incident.compute_etag())

        patch_data = await parse_merge_patch_body(request, IncidentPatch)

        new_service_id = incident.service_id
        if patch_data.service_id is not msgspec.UNSET:
            if patch_data.service_id is None:
                raise ProblemException(
                    status_code=422,
                    title="Unprocessable Content",
                    detail="Field 'service_id' cannot be null.",
                    type_slug="non-nullable-field",
                )
            new_service_id = patch_data.service_id

        new_release_id = (
            incident.release_id
            if patch_data.release_id is msgspec.UNSET
            else patch_data.release_id
        )
        await _validate_service_and_release_relation(
            db_session, new_service_id, new_release_id
        )

        new_severity = (
            incident.severity
            if patch_data.severity is msgspec.UNSET
            else patch_data.severity
        )
        new_status = (
            incident.status if patch_data.status is msgspec.UNSET else patch_data.status
        )
        if new_severity is None or new_status is None:
            raise ProblemException(
                status_code=422,
                title="Unprocessable Content",
                detail="Fields 'severity' and 'status' cannot be null.",
                type_slug="non-nullable-field",
            )
        validate_incident_fields(new_severity, new_status)

        for field_name in ("title", "summary"):
            val = getattr(patch_data, field_name)
            if val is not msgspec.UNSET:
                if val is None:
                    raise ProblemException(
                        status_code=422,
                        title="Unprocessable Content",
                        detail=f"Field '{field_name}' cannot be null.",
                        type_slug="non-nullable-field",
                    )
                setattr(incident, field_name, val.strip())

        incident.service_id = new_service_id
        incident.release_id = new_release_id
        incident.severity = new_severity
        incident.status = new_status

        if patch_data.resolution_notes is not msgspec.UNSET:
            incident.resolution_notes = patch_data.resolution_notes

        incident.updated_at = utc_now()
        await db_session.commit()
        await db_session.refresh(incident)

        payload = serialize_incident_hal(incident, user)
        etag = incident.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=incident.updated_at)
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="incident"
        )

    @delete(
        path="/{incident_id:int}",
        status_code=204,
        guards=[require_writer],
        summary="Delete an Incident (Owner or Admin)",
    )
    async def delete_incident(
        self,
        request: Request,
        db_session: AsyncSession,
        incident_id: int,
    ) -> None:
        incident = await _get_incident_or_404(db_session, incident_id)
        ensure_owner_or_admin(request.scope.get("user"), incident.reported_by)
        verify_if_match(request, incident.compute_etag())
        await db_session.delete(incident)
        await db_session.commit()

    @route(
        path="/{incident_id:int}",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for a single Incident",
    )
    async def options_incident_item(self, incident_id: int) -> Response:
        return build_options_response(
            ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"],
            supports_merge_patch=True,
        )
