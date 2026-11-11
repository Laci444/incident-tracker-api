from typing import Any

import msgspec

from app.core.exceptions import ProblemException
from app.core.hypermedia import hal_link
from app.db.models import ReleaseModel
from app.schemas.common import ALLOWED_ENVIRONMENTS
from app.security.auth import AuthenticatedUser


class ReleaseCreate(msgspec.Struct, kw_only=True):
    version: str
    commit_sha: str
    environment: str = "production"
    release_notes: str | None = None


class ReleasePatch(msgspec.Struct, kw_only=True):
    version: str | None | msgspec.UnsetType = msgspec.UNSET
    commit_sha: str | None | msgspec.UnsetType = msgspec.UNSET
    environment: str | None | msgspec.UnsetType = msgspec.UNSET
    release_notes: str | None | msgspec.UnsetType = msgspec.UNSET


def validate_release_environment(environment: str) -> None:
    if environment not in ALLOWED_ENVIRONMENTS:
        raise ProblemException(
            status_code=422,
            title="Unprocessable Content",
            detail=f"Invalid environment '{environment}'. Allowed values: {sorted(ALLOWED_ENVIRONMENTS)}.",
            type_slug="invalid-release-environment",
        )


def serialize_release_hal(
    release: ReleaseModel,
    user: AuthenticatedUser | None = None,
) -> dict[str, Any]:
    self_uri = f"/api/releases/{release.id}"
    service_uri = f"/api/services/{release.service_id}"

    links: dict[str, Any] = {
        "self": hal_link(self_uri, title=f"Release {release.version}"),
        "collection": hal_link(
            f"{service_uri}/releases", title="Service Releases Collection"
        ),
        "up": hal_link(service_uri, title="Parent Service"),
        "related": hal_link(
            f"/api/incidents?service_id={release.service_id}", title="Service Incidents"
        ),
        "describedby": hal_link("/schema/openapi.json", title="OpenAPI Specification"),
    }

    can_modify = user is not None and (
        user.role == "admin"
        or (user.role == "developer" and user.username == release.deployed_by)
    )
    if can_modify:
        links["edit"] = hal_link(self_uri, title="Patch Release", method="PATCH")
        links["delete"] = hal_link(self_uri, title="Delete Release", method="DELETE")

    return {
        "id": release.id,
        "service_id": release.service_id,
        "version": release.version,
        "commit_sha": release.commit_sha,
        "environment": release.environment,
        "release_notes": release.release_notes,
        "deployed_by": release.deployed_by,
        "created_at": release.created_at.isoformat(),
        "updated_at": release.updated_at.isoformat(),
        "_links": links,
    }
