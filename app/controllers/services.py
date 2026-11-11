from typing import Any

import msgspec
from litestar import Controller, Request, Response, delete, post, put, route
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.db.models import ServiceModel, utc_now
from app.schemas.common import merge_patch_openapi_body, parse_merge_patch_body
from app.schemas.service import (
    ServiceCreate,
    ServicePatch,
    ServiceUpdate,
    serialize_service_hal,
    validate_service_tier,
)
from app.security.auth import AuthenticatedUser
from app.security.guards import require_admin, require_writer


async def _get_service_or_404(
    db_session: AsyncSession, service_id: int
) -> ServiceModel:
    service = await db_session.get(ServiceModel, service_id)
    if service is None:
        raise ProblemException(
            status_code=404,
            title="Resource Not Found",
            detail=f"Service with id={service_id} does not exist.",
            type_slug="service-not-found",
        )
    return service


class ServiceController(Controller):
    path = "/api/services"
    tags = ["2. Services"]

    @route(
        path="",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="List Services (with pagination & filtering)",
    )
    async def list_services(
        self,
        request: Request,
        db_session: AsyncSession,
        tier: str | None = None,
        is_active: bool | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Response:
        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        stmt = select(ServiceModel).order_by(ServiceModel.id)
        count_stmt = select(func.count(ServiceModel.id))

        if tier is not None:
            stmt = stmt.where(ServiceModel.tier == tier)
            count_stmt = count_stmt.where(ServiceModel.tier == tier)
        if is_active is not None:
            stmt = stmt.where(ServiceModel.is_active == is_active)
            count_stmt = count_stmt.where(ServiceModel.is_active == is_active)

        total: int = (await db_session.scalar(count_stmt)) or 0
        services = list(
            (await db_session.scalars(stmt.limit(limit).offset(offset))).all()
        )

        user: AuthenticatedUser | None = request.scope.get("user")
        embedded_items = [serialize_service_hal(svc, user) for svc in services]

        links: dict[str, Any] = {
            "self": hal_link(
                f"/api/services?limit={limit}&offset={offset}",
                title="Services Collection",
            ),
            "up": hal_link("/api", title="API Entry Point"),
            "first": hal_link(
                f"/api/services?limit={limit}&offset=0", title="First Page"
            ),
            "item": [
                hal_link(f"/api/services/{svc.id}", title=svc.name) for svc in services
            ],
            "describedby": hal_link(
                "/schema/openapi.json", title="OpenAPI Specification"
            ),
        }
        if offset + limit < total:
            links["next"] = hal_link(
                f"/api/services?limit={limit}&offset={offset + limit}",
                title="Next Page",
            )
        if offset > 0:
            prev_offset = max(0, offset - limit)
            links["prev"] = hal_link(
                f"/api/services?limit={limit}&offset={prev_offset}",
                title="Previous Page",
            )
        if user and user.role in ("admin", "developer"):
            links["create-form"] = hal_link(
                "/api/services", title="Register New Service", method="POST"
            )

        payload = {
            "total": total,
            "count": len(embedded_items),
            "limit": limit,
            "offset": offset,
            "_links": links,
            "_embedded": {"services": embedded_items},
        }

        etag = compute_payload_etag(payload)
        cond_response = evaluate_conditional_get(request, etag=etag)
        if cond_response is not None:
            return cond_response

        headers = build_cache_headers(etag=etag, max_age=30)
        headers["Link"] = format_rfc8288_link_header(links)
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="services"
        )

    @post(
        path="",
        status_code=201,
        guards=[require_writer],
        summary="Create a new Service",
    )
    async def create_service(
        self,
        request: Request,
        db_session: AsyncSession,
        data: ServiceCreate,
    ) -> Response:
        validate_service_tier(data.tier)

        service = ServiceModel(
            name=data.name.strip(),
            slug=data.slug.strip().lower(),
            description=data.description.strip(),
            owner_team=data.owner_team.strip(),
            tier=data.tier,
            is_active=data.is_active,
        )
        db_session.add(service)
        try:
            await db_session.commit()
            await db_session.refresh(service)
        except IntegrityError as exc:
            await db_session.rollback()
            raise ProblemException(
                status_code=409,
                title="Conflict",
                detail=f"A service with name '{data.name}' or slug '{data.slug}' already exists.",
                type_slug="duplicate-service",
            ) from exc

        user: AuthenticatedUser | None = request.scope.get("user")
        payload = serialize_service_hal(service, user)
        etag = service.compute_etag()

        headers = build_cache_headers(etag=etag, last_modified=service.updated_at)
        headers["Location"] = f"/api/services/{service.id}"
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=201, headers=headers, xml_root="service"
        )

    @route(
        path="",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for Services Collection",
    )
    async def options_services_collection(self) -> Response:
        return build_options_response(["GET", "HEAD", "POST", "OPTIONS"])

    @route(
        path="/{service_id:int}",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="Get a single Service by ID",
    )
    async def get_service(
        self,
        request: Request,
        db_session: AsyncSession,
        service_id: int,
    ) -> Response:
        service = await _get_service_or_404(db_session, service_id)
        etag = service.compute_etag()

        cond_response = evaluate_conditional_get(
            request, etag=etag, last_modified=service.updated_at
        )
        if cond_response is not None:
            return cond_response

        user: AuthenticatedUser | None = request.scope.get("user")
        payload = serialize_service_hal(service, user)

        headers = build_cache_headers(
            etag=etag, last_modified=service.updated_at, max_age=60
        )
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="service"
        )

    @put(
        path="/{service_id:int}",
        status_code=200,
        guards=[require_writer],
        summary="Replace a Service (Full Update)",
    )
    async def replace_service(
        self,
        request: Request,
        db_session: AsyncSession,
        service_id: int,
        data: ServiceUpdate,
    ) -> Response:
        service = await _get_service_or_404(db_session, service_id)
        verify_if_match(request, service.compute_etag())
        validate_service_tier(data.tier)

        service.name = data.name.strip()
        service.slug = data.slug.strip().lower()
        service.description = data.description.strip()
        service.owner_team = data.owner_team.strip()
        service.tier = data.tier
        service.is_active = data.is_active
        service.updated_at = utc_now()

        try:
            await db_session.commit()
            await db_session.refresh(service)
        except IntegrityError as exc:
            await db_session.rollback()
            raise ProblemException(
                status_code=409,
                title="Conflict",
                detail="Service name or slug conflicts with an existing service.",
                type_slug="duplicate-service",
            ) from exc

        user: AuthenticatedUser | None = request.scope.get("user")
        payload = serialize_service_hal(service, user)
        etag = service.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=service.updated_at)
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="service"
        )

    @route(
        path="/{service_id:int}",
        http_method=["PATCH"],
        status_code=200,
        guards=[require_writer],
        summary="Partially update a Service (RFC 7396 JSON Merge Patch)",
        openapi_extra=merge_patch_openapi_body(
            {"tier": "tier-2", "owner_team": "Core Reliability", "is_active": False}
        ),
    )
    async def patch_service(
        self,
        request: Request,
        db_session: AsyncSession,
        service_id: int,
    ) -> Response:
        service = await _get_service_or_404(db_session, service_id)
        verify_if_match(request, service.compute_etag())

        patch_data = await parse_merge_patch_body(request, ServicePatch)

        for field_name in (
            "name",
            "slug",
            "description",
            "owner_team",
            "tier",
            "is_active",
        ):
            val = getattr(patch_data, field_name)
            if val is not msgspec.UNSET:
                if val is None:
                    raise ProblemException(
                        status_code=422,
                        title="Unprocessable Content",
                        detail=f"Field '{field_name}' is non-nullable and cannot be removed via null.",
                        type_slug="non-nullable-field",
                    )
                if field_name == "tier":
                    validate_service_tier(val)
                if isinstance(val, str):
                    val = val.strip().lower() if field_name == "slug" else val.strip()
                setattr(service, field_name, val)

        service.updated_at = utc_now()
        try:
            await db_session.commit()
            await db_session.refresh(service)
        except IntegrityError as exc:
            await db_session.rollback()
            raise ProblemException(
                status_code=409,
                title="Conflict",
                detail="Patched name or slug conflicts with an existing service.",
                type_slug="duplicate-service",
            ) from exc

        user: AuthenticatedUser | None = request.scope.get("user")
        payload = serialize_service_hal(service, user)
        etag = service.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=service.updated_at)
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="service"
        )

    @delete(
        path="/{service_id:int}",
        status_code=204,
        guards=[require_admin],
        summary="Delete a Service (Admin only)",
    )
    async def delete_service(
        self,
        request: Request,
        db_session: AsyncSession,
        service_id: int,
    ) -> None:
        service = await _get_service_or_404(db_session, service_id)
        verify_if_match(request, service.compute_etag())
        await db_session.delete(service)
        await db_session.commit()

    @route(
        path="/{service_id:int}",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for a single Service",
    )
    async def options_service_item(self) -> Response:
        return build_options_response(
            ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"],
            supports_merge_patch=True,
        )
