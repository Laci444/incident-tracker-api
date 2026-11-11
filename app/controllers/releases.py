from typing import Any

import msgspec
from litestar import Controller, Request, Response, delete, post, route
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.db.models import ReleaseModel, utc_now
from app.schemas.common import merge_patch_openapi_body, parse_merge_patch_body
from app.schemas.release import (
    ReleaseCreate,
    ReleasePatch,
    serialize_release_hal,
    validate_release_environment,
)
from app.security.auth import AuthenticatedUser
from app.security.guards import ensure_owner_or_admin, require_writer


async def _get_release_or_404(
    db_session: AsyncSession, release_id: int
) -> ReleaseModel:
    release = await db_session.get(ReleaseModel, release_id)
    if release is None:
        raise ProblemException(
            status_code=404,
            title="Resource Not Found",
            detail=f"Release with id={release_id} does not exist.",
            type_slug="release-not-found",
        )
    return release


class ReleaseController(Controller):
    path = "/api"
    tags = ["3. Releases"]

    @route(
        path="/services/{service_id:int}/releases",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="List Releases for a specific Service",
    )
    async def list_service_releases(
        self,
        request: Request,
        db_session: AsyncSession,
        service_id: int,
    ) -> Response:
        service = await _get_service_or_404(db_session, service_id)
        stmt = (
            select(ReleaseModel)
            .where(ReleaseModel.service_id == service_id)
            .order_by(ReleaseModel.id.desc())
        )
        releases = list((await db_session.scalars(stmt)).all())

        user: AuthenticatedUser | None = request.scope.get("user")
        embedded = [serialize_release_hal(rel, user) for rel in releases]
        self_uri = f"/api/services/{service_id}/releases"

        links: dict[str, Any] = {
            "self": hal_link(self_uri, title=f"Releases for {service.name}"),
            "up": hal_link(f"/api/services/{service_id}", title=service.name),
            "item": [
                hal_link(
                    f"/api/releases/{rel.id}", title=f"{service.slug} {rel.version}"
                )
                for rel in releases
            ],
            "describedby": hal_link(
                "/schema/openapi.json", title="OpenAPI Specification"
            ),
        }
        if user and user.role in ("admin", "developer"):
            links["create-form"] = hal_link(
                self_uri, title="Deploy New Release", method="POST"
            )

        payload = {
            "service_id": service.id,
            "service_name": service.name,
            "count": len(embedded),
            "_links": links,
            "_embedded": {"releases": embedded},
        }

        etag = compute_payload_etag(payload)
        cond_response = evaluate_conditional_get(request, etag=etag)
        if cond_response is not None:
            return cond_response

        headers = build_cache_headers(etag=etag, max_age=30)
        headers["Link"] = format_rfc8288_link_header(links)
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="releases"
        )

    @post(
        path="/services/{service_id:int}/releases",
        status_code=201,
        guards=[require_writer],
        summary="Create a new Release for a Service",
    )
    async def create_service_release(
        self,
        request: Request,
        db_session: AsyncSession,
        service_id: int,
        data: ReleaseCreate,
    ) -> Response:
        await _get_service_or_404(db_session, service_id)
        validate_release_environment(data.environment)

        user: AuthenticatedUser = request.user
        release = ReleaseModel(
            service_id=service_id,
            version=data.version.strip(),
            commit_sha=data.commit_sha.strip(),
            environment=data.environment,
            release_notes=data.release_notes,
            deployed_by=user.username,
        )
        db_session.add(release)
        await db_session.commit()
        await db_session.refresh(release)

        payload = serialize_release_hal(release, user)
        etag = release.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=release.updated_at)
        headers["Location"] = f"/api/releases/{release.id}"
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=201, headers=headers, xml_root="release"
        )

    @route(
        path="/services/{service_id:int}/releases",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for Service Releases Collection",
    )
    async def options_service_releases(self, service_id: int) -> Response:
        return build_options_response(["GET", "HEAD", "POST", "OPTIONS"])

    @route(
        path="/releases/{release_id:int}",
        http_method=["GET", "HEAD"],
        status_code=200,
        summary="Get a single Release by ID",
    )
    async def get_release(
        self,
        request: Request,
        db_session: AsyncSession,
        release_id: int,
    ) -> Response:
        release = await _get_release_or_404(db_session, release_id)
        etag = release.compute_etag()

        cond_response = evaluate_conditional_get(
            request, etag=etag, last_modified=release.updated_at
        )
        if cond_response is not None:
            return cond_response

        user: AuthenticatedUser | None = request.scope.get("user")
        payload = serialize_release_hal(release, user)
        headers = build_cache_headers(
            etag=etag, last_modified=release.updated_at, max_age=60
        )
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="release"
        )

    @route(
        path="/releases/{release_id:int}",
        http_method=["PATCH"],
        status_code=200,
        guards=[require_writer],
        summary="Partially update a Release (RFC 7396 JSON Merge Patch)",
        openapi_extra=merge_patch_openapi_body(
            {"environment": "production", "release_notes": None}
        ),
    )
    async def patch_release(
        self,
        request: Request,
        db_session: AsyncSession,
        release_id: int,
    ) -> Response:
        release = await _get_release_or_404(db_session, release_id)
        user: AuthenticatedUser | None = request.scope.get("user")
        ensure_owner_or_admin(user, release.deployed_by)
        verify_if_match(request, release.compute_etag())

        patch_data = await parse_merge_patch_body(request, ReleasePatch)

        for field_name in ("version", "commit_sha", "environment"):
            val = getattr(patch_data, field_name)
            if val is not msgspec.UNSET:
                if val is None:
                    raise ProblemException(
                        status_code=422,
                        title="Unprocessable Content",
                        detail=f"Field '{field_name}' cannot be set to null.",
                        type_slug="non-nullable-field",
                    )
                if field_name == "environment":
                    validate_release_environment(val)
                setattr(release, field_name, val.strip())

        # RFC 7396: nullable release_notes can be updated OR cleared by passing {"release_notes": null}
        if patch_data.release_notes is not msgspec.UNSET:
            release.release_notes = patch_data.release_notes

        release.updated_at = utc_now()
        await db_session.commit()
        await db_session.refresh(release)

        payload = serialize_release_hal(release, user)
        etag = release.compute_etag()
        headers = build_cache_headers(etag=etag, last_modified=release.updated_at)
        headers["Link"] = format_rfc8288_link_header(payload["_links"])
        return render_resource_response(
            request, payload, status_code=200, headers=headers, xml_root="release"
        )

    @delete(
        path="/releases/{release_id:int}",
        status_code=204,
        guards=[require_writer],
        summary="Delete a Release (Owner or Admin)",
    )
    async def delete_release(
        self,
        request: Request,
        db_session: AsyncSession,
        release_id: int,
    ) -> None:
        release = await _get_release_or_404(db_session, release_id)
        ensure_owner_or_admin(request.scope.get("user"), release.deployed_by)
        verify_if_match(request, release.compute_etag())
        await db_session.delete(release)
        await db_session.commit()

    @route(
        path="/releases/{release_id:int}",
        http_method=["OPTIONS"],
        status_code=204,
        summary="OPTIONS for a single Release",
    )
    async def options_release_item(self, release_id: int) -> Response:
        return build_options_response(
            ["GET", "HEAD", "PATCH", "DELETE", "OPTIONS"],
            supports_merge_patch=True,
        )
