from typing import Any

import msgspec

from app.core.exceptions import ProblemException
from app.core.hypermedia import hal_link
from app.db.models import IncidentModel
from app.schemas.common import ALLOWED_SEVERITIES, ALLOWED_STATUSES
from app.security.auth import AuthenticatedUser


class IncidentCreate(msgspec.Struct, kw_only=True):
    service_id: int
    title: str
    summary: str
    severity: str = "medium"
    status: str = "open"
    release_id: int | None = None
    resolution_notes: str | None = None


class IncidentUpdate(msgspec.Struct, kw_only=True):
    service_id: int
    release_id: int | None
    title: str
    summary: str
    severity: str
    status: str
    resolution_notes: str | None


class IncidentPatch(msgspec.Struct, kw_only=True):
    service_id: int | None | msgspec.UnsetType = msgspec.UNSET
    release_id: int | None | msgspec.UnsetType = msgspec.UNSET
    title: str | None | msgspec.UnsetType = msgspec.UNSET
    summary: str | None | msgspec.UnsetType = msgspec.UNSET
    severity: str | None | msgspec.UnsetType = msgspec.UNSET
    status: str | None | msgspec.UnsetType = msgspec.UNSET
    resolution_notes: str | None | msgspec.UnsetType = msgspec.UNSET


def validate_incident_fields(severity: str, status: str) -> None:
    if severity not in ALLOWED_SEVERITIES:
        raise ProblemException(
            status_code=422,
            title="Unprocessable Content",
            detail=f"Invalid severity '{severity}'. Allowed values: {sorted(ALLOWED_SEVERITIES)}.",
            type_slug="invalid-incident-severity",
        )
    if status not in ALLOWED_STATUSES:
        raise ProblemException(
            status_code=422,
            title="Unprocessable Content",
            detail=f"Invalid status '{status}'. Allowed values: {sorted(ALLOWED_STATUSES)}.",
            type_slug="invalid-incident-status",
        )


def serialize_incident_hal(
    incident: IncidentModel,
    user: AuthenticatedUser | None = None,
) -> dict[str, Any]:
    self_uri = f"/api/incidents/{incident.id}"
    service_uri = f"/api/services/{incident.service_id}"

    links: dict[str, Any] = {
        "self": hal_link(self_uri, title=incident.title),
        "collection": hal_link("/api/incidents", title="All Incidents"),
        "up": hal_link(service_uri, title="Affected Service"),
        "describedby": hal_link("/schema/openapi.json", title="OpenAPI Specification"),
    }

    if incident.release_id is not None:
        links["related"] = hal_link(
            f"/api/releases/{incident.release_id}",
            title="Suspect Release",
        )

    if user is not None and user.username == incident.reported_by:
        links["author"] = hal_link("/api/me", title=f"Reporter ({incident.reported_by})")

    can_modify = user is not None and (
        user.role == "admin" or (user.role == "developer" and user.username == incident.reported_by)
    )
    if can_modify:
        links["edit"] = hal_link(self_uri, title="Update or Patch Incident", method="PATCH")
        links["delete"] = hal_link(self_uri, title="Delete Incident", method="DELETE")

    return {
        "id": incident.id,
        "service_id": incident.service_id,
        "release_id": incident.release_id,
        "title": incident.title,
        "summary": incident.summary,
        "severity": incident.severity,
        "status": incident.status,
        "resolution_notes": incident.resolution_notes,
        "reported_by": incident.reported_by,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
        "_links": links,
    }
