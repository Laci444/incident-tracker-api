from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ServiceTier
from app.db.models import ServiceModel
from app.repositories.base import BaseRepository, PageResult
from app.schemas.service import ServiceCreate, ServiceUpdate


class ServiceCatalogService:
    """Pure business logic for managing cloud services."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.repo = BaseRepository(db_session, ServiceModel)

    async def list_services(
        self,
        *,
        tier: ServiceTier | None = None,
        is_active: bool | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> PageResult[ServiceModel]:
        filters: list[Any] = []
        if tier is not None:
            filters.append(ServiceModel.tier == tier)
        if is_active is not None:
            filters.append(ServiceModel.is_active == is_active)

        return await self.repo.paginate(
            filters=filters,
            order_by=ServiceModel.id.asc(),
            limit=limit,
            offset=offset,
        )

    async def get_service(self, service_id: int) -> ServiceModel:
        return await self.repo.get_or_404(service_id)

    async def create_service(self, data: ServiceCreate) -> ServiceModel:
        service = ServiceModel(
            name=data.name.strip(),
            slug=data.slug.strip().lower(),
            description=data.description.strip(),
            owner_team=data.owner_team.strip(),
            tier=data.tier,
            is_active=data.is_active,
        )
        return await self.repo.save(
            service,
            conflict_detail=f"A service with name '{data.name}' or slug '{data.slug}' already exists.",
        )

    async def replace_service(
        self, service_id: int, data: ServiceUpdate
    ) -> ServiceModel:
        service = await self.repo.get_or_404(service_id)
        changes = {
            "name": data.name.strip(),
            "slug": data.slug.strip().lower(),
            "description": data.description.strip(),
            "owner_team": data.owner_team.strip(),
            "tier": data.tier,
            "is_active": data.is_active,
        }
        return await self.repo.apply_changes(
            service,
            changes,
            conflict_detail="Service name or slug conflicts with an existing service.",
        )

    async def patch_service(
        self, service_id: int, changes: dict[str, Any]
    ) -> ServiceModel:
        service = await self.repo.get_or_404(service_id)
        return await self.repo.apply_changes(
            service,
            changes,
            conflict_detail="Patched name or slug conflicts with an existing service.",
        )

    async def delete_service(self, service_id: int) -> None:
        service = await self.repo.get_or_404(service_id)
        await self.repo.delete(service)
