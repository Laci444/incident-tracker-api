from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PathParam
from app.db.models import ReleaseModel, ServiceModel
from app.repositories.base import BaseRepository, PageResult
from app.schemas.release import ReleaseCreate
from app.security.auth import AuthenticatedUser
from app.security.guards import ensure_owner_or_admin


class ReleaseService:
    """Pure business logic for managing service releases."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.repo = BaseRepository(db_session, ReleaseModel)
        self.service_repo = BaseRepository(db_session, ServiceModel)

    async def list_service_releases(
        self,
        service_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> PageResult[ReleaseModel]:
        service = await self.service_repo.get_or_404(service_id)
        return await self.repo.paginate(
            filters=[ReleaseModel.service_id == service_id],
            order_by=ReleaseModel.id.desc(),
            limit=limit,
            offset=offset,
            route_params={PathParam.SERVICE_ID.value: service_id},
            extra_metadata={"service_id": service.id, "service_name": service.name},
        )

    async def get_release(self, release_id: int) -> ReleaseModel:
        return await self.repo.get_or_404(release_id)

    async def create_release(
        self,
        service_id: int,
        data: ReleaseCreate,
        actor: AuthenticatedUser,
    ) -> ReleaseModel:
        await self.service_repo.get_or_404(service_id)
        release = ReleaseModel(
            service_id=service_id,
            version=data.version.strip(),
            commit_sha=data.commit_sha.strip(),
            environment=data.environment,
            release_notes=data.release_notes,
            deployed_by=actor.username,
        )
        return await self.repo.save(
            release,
            conflict_detail="Failed to persist release due to a constraint conflict.",
        )

    async def patch_release(
        self,
        release_id: int,
        changes: dict[str, Any],
        actor: AuthenticatedUser | None,
    ) -> ReleaseModel:
        release = await self.repo.get_or_404(release_id)
        ensure_owner_or_admin(actor, release.deployed_by)
        return await self.repo.apply_changes(release, changes)

    async def delete_release(
        self,
        release_id: int,
        actor: AuthenticatedUser | None,
    ) -> None:
        release = await self.repo.get_or_404(release_id)
        ensure_owner_or_admin(actor, release.deployed_by)
        await self.repo.delete(release)
