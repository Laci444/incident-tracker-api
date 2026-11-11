from typing import Any

import msgspec

from app.core.exceptions import ProblemException
from app.core.hypermedia import hal_link
from app.db.models import ServiceModel
from app.schemas.common import ALLOWED_TIERS
from app.security.auth import AuthenticatedUser


class ServiceCreate(msgspec.Struct, kw_only=True):
    name: str
    slug: str
    description: str
    owner_team: str
    tier: str = "tier-1"
    is_active: bool = True


class ServiceUpdate(msgspec.Struct, kw_only=True):
    name: str
    slug: str
    description: str
    owner_team: str
    tier: str
    is_active: bool


class ServicePatch(msgspec.Struct, kw_only=True):
    name: str | None | msgspec.UnsetType = msgspec.UNSET
    slug: str | None | msgspec.UnsetType = msgspec.UNSET
    description: str | None | msgspec.UnsetType = msgspec.UNSET
    owner_team: str | None | msgspec.UnsetType = msgspec.UNSET
    tier: str | None | msgspec.UnsetType = msgspec.UNSET
    is_active: bool | None | msgspec.UnsetType = msgspec.UNSET


def validate_service_tier(tier: str) -> None:
    if tier not in ALLOWED_TIERS:
        raise ProblemException(
            status_code=422,
            title="Unprocessable Content",
            detail=f"Invalid service tier '{tier}'. Allowed values: {sorted(ALLOWED_TIERS)}.",
            type_slug="invalid-service-tier",
        )


def serialize_service_hal(
    service: ServiceModel,
    user: AuthenticatedUser | None = None,
) -> dict[str, Any]:
    self_uri = f"/api/services/{service.id}"
    links: dict[str, Any] = {
        "self": hal_link(self_uri, title=service.name),
        "collection": hal_link("/api/services", title="All Services"),
        "up": hal_link("/api", title="API Entry Point"),
        "releases": hal_link(
            f"{self_uri}/releases", title=f"Releases for {service.name}"
        ),
        "incidents": hal_link(
            f"/api/incidents?service_id={service.id}",
            title=f"Incidents for {service.name}",
        ),
        "describedby": hal_link("/schema/openapi.json", title="OpenAPI Specification"),
    }

    # Dynamic HATEOAS: expose state-changing links based on user role
    if user and user.role in ("admin", "developer"):
        links["edit"] = hal_link(
            self_uri, title="Update or Patch Service", method="PATCH"
        )
    if user and user.role == "admin":
        links["delete"] = hal_link(self_uri, title="Delete Service", method="DELETE")

    return {
        "id": service.id,
        "name": service.name,
        "slug": service.slug,
        "description": service.description,
        "tier": service.tier,
        "owner_team": service.owner_team,
        "is_active": service.is_active,
        "created_at": service.created_at.isoformat(),
        "updated_at": service.updated_at.isoformat(),
        "_links": links,
    }
