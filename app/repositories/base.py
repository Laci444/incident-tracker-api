from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RouteName
from app.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.db.models import BaseResourceModel, utc_now

ModelT = TypeVar("ModelT", bound=BaseResourceModel)


@dataclass(frozen=True)
class PageResult(Generic[ModelT]):
    """Domain container for a paginated collection of resources."""

    items: list[ModelT]
    total: int
    limit: int
    offset: int
    model_cls: type[ModelT]
    collection_route: RouteName
    create_route: RouteName | None = None
    route_params: dict[str, Any] = field(default_factory=dict)
    extra_metadata: dict[str, Any] = field(default_factory=dict)


class BaseRepository(Generic[ModelT]):
    """Generic asynchronous SQLAlchemy repository eliminating CRUD boilerplate."""

    def __init__(self, session: AsyncSession, model_cls: type[ModelT]) -> None:
        self.session = session
        self.model_cls = model_cls

    async def get_or_404(self, entity_id: int) -> ModelT:
        instance = await self.session.get(self.model_cls, entity_id)
        if instance is None:
            resource_label = self.model_cls.__resource_meta__.resource_name.value
            raise ResourceNotFoundError(resource_label, entity_id)
        return instance

    async def paginate(
        self,
        *,
        filters: Sequence[Any] = (),
        order_by: Any = None,
        limit: int = 10,
        offset: int = 0,
        route_params: dict[str, Any] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> PageResult[ModelT]:
        stmt = select(self.model_cls)
        count_stmt = select(func.count(self.model_cls.id))

        for condition in filters:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(
            order_by if order_by is not None else self.model_cls.id.asc()
        )

        total: int = (await self.session.scalar(count_stmt)) or 0
        items = list(
            (await self.session.scalars(stmt.limit(limit).offset(offset))).all()
        )

        meta = self.model_cls.__resource_meta__
        return PageResult(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            model_cls=self.model_cls,
            collection_route=meta.collection_route,
            create_route=meta.create_route,
            route_params=dict(route_params or {}),
            extra_metadata=dict(extra_metadata or {}),
        )

    async def save(self, instance: ModelT, *, conflict_detail: str) -> ModelT:
        self.session.add(instance)
        try:
            await self.session.commit()
            await self.session.refresh(instance)
            return instance
        except IntegrityError as exc:
            await self.session.rollback()
            err_msg = str(exc.orig).lower() if exc.orig else str(exc).lower()
            if "check constraint" in err_msg:
                raise ValidationFailedError(
                    f"Database check constraint failed: {exc.orig}"
                ) from exc
            raise ResourceConflictError(conflict_detail) from exc

    async def apply_changes(
        self,
        instance: ModelT,
        changes: dict[str, Any],
        *,
        conflict_detail: str = "Resource update violated a uniqueness constraint.",
    ) -> ModelT:
        for field_name, value in changes.items():
            setattr(instance, field_name, value)
        instance.updated_at = utc_now()
        return await self.save(instance, conflict_detail=conflict_detail)

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.commit()
