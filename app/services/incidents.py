from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import IncidentSeverity, IncidentStatus
from app.core.exceptions import ValidationFailedError
from app.db.models import IncidentModel, ReleaseModel, ServiceModel
from app.repositories.base import BaseRepository, PageResult
from app.schemas.incident import IncidentCreate, IncidentUpdate
from app.security.auth import AuthenticatedUser
from app.security.guards import ensure_owner_or_admin


class IncidentService:
    """Pure business logic for managing operational incidents."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.repo = BaseRepository(db_session, IncidentModel)
        self.service_repo = BaseRepository(db_session, ServiceModel)
        self.release_repo = BaseRepository(db_session, ReleaseModel)

    async def _verify_service_and_release_link(
        self, service_id: int, release_id: int | None
    ) -> None:
        await self.service_repo.get_or_404(service_id)
        if release_id is not None:
            release = await self.release_repo.get_or_404(release_id)
            if release.service_id != service_id:
                raise ValidationFailedError(
                    f"Release id='{release_id}' belongs to service id='{release.service_id}', "
                    f"not service id='{service_id}'."
                )

    async def list_incidents(
        self,
        *,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
        service_id: int | None = None,
        release_id: int | None = None,
        reported_by: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> PageResult[IncidentModel]:
        filters: list[Any] = []
        if status is not None:
            filters.append(IncidentModel.status == status)
        if severity is not None:
            filters.append(IncidentModel.severity == severity)
        if service_id is not None:
            filters.append(IncidentModel.service_id == service_id)
        if release_id is not None:
            filters.append(IncidentModel.release_id == release_id)
        if reported_by is not None:
            filters.append(IncidentModel.reported_by == reported_by)

        return await self.repo.paginate(
            filters=filters,
            order_by=IncidentModel.id.desc(),
            limit=limit,
            offset=offset,
        )

    async def get_incident(self, incident_id: int) -> IncidentModel:
        return await self.repo.get_or_404(incident_id)

    async def create_incident(
        self,
        data: IncidentCreate,
        actor: AuthenticatedUser,
    ) -> IncidentModel:
        await self._verify_service_and_release_link(data.service_id, data.release_id)
        incident = IncidentModel(
            service_id=data.service_id,
            release_id=data.release_id,
            title=data.title.strip(),
            summary=data.summary.strip(),
            severity=data.severity,
            status=data.status,
            resolution_notes=data.resolution_notes,
            reported_by=actor.username,
        )
        return await self.repo.save(
            incident,
            conflict_detail="Failed to create incident due to a constraint violation.",
        )

    async def replace_incident(
        self,
        incident_id: int,
        data: IncidentUpdate,
        actor: AuthenticatedUser | None,
    ) -> IncidentModel:
        incident = await self.repo.get_or_404(incident_id)
        ensure_owner_or_admin(actor, incident.reported_by)
        await self._verify_service_and_release_link(data.service_id, data.release_id)

        changes = {
            "service_id": data.service_id,
            "release_id": data.release_id,
            "title": data.title.strip(),
            "summary": data.summary.strip(),
            "severity": data.severity,
            "status": data.status,
            "resolution_notes": data.resolution_notes,
        }
        return await self.repo.apply_changes(incident, changes)

    async def patch_incident(
        self,
        incident_id: int,
        changes: dict[str, Any],
        actor: AuthenticatedUser | None,
    ) -> IncidentModel:
        incident = await self.repo.get_or_404(incident_id)
        ensure_owner_or_admin(actor, incident.reported_by)

        target_service_id = changes.get("service_id", incident.service_id)
        target_release_id = changes.get("release_id", incident.release_id)
        await self._verify_service_and_release_link(
            target_service_id, target_release_id
        )

        return await self.repo.apply_changes(incident, changes)

    async def delete_incident(
        self,
        incident_id: int,
        actor: AuthenticatedUser | None,
    ) -> None:
        incident = await self.repo.get_or_404(incident_id)
        ensure_owner_or_admin(actor, incident.reported_by)
        await self.repo.delete(incident)
