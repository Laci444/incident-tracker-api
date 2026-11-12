import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    inspect,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    CollectionName,
    IncidentSeverity,
    IncidentStatus,
    PathParam,
    ReleaseEnvironment,
    ResourceName,
    RouteName,
    ServiceTier,
)
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _sa_str_enum(enum_cls: type[StrEnum], constraint_name: str) -> SAEnum:
    """Binds a Python StrEnum to a database CHECK constraint using enum values."""
    return SAEnum(
        enum_cls,
        name=constraint_name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


@dataclass(frozen=True)
class ResourceMetadata:
    """Declarative, HTTP-agnostic metadata describing a domain resource."""

    resource_name: ResourceName
    collection_name: CollectionName
    id_param: PathParam
    detail_route: RouteName
    collection_route: RouteName
    create_route: RouteName
    patch_route: RouteName
    delete_route: RouteName
    replace_route: RouteName | None = None
    parent_id_field: str | None = None
    parent_id_param: PathParam | None = None
    owner_field: str | None = None
    delete_admin_only: bool = False
    title_field: str = "name"


class BaseResourceModel(Base):
    """Abstract base model providing ETag computation and dictionary serialization."""

    __abstract__ = True
    __resource_meta__: ClassVar[ResourceMetadata]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    def to_dict(self) -> dict[str, Any]:
        mapper = inspect(self.__class__)
        result: dict[str, Any] = {}
        for column in mapper.columns:
            val = getattr(self, column.key)
            if isinstance(val, datetime):
                result[column.key] = val.isoformat()
            elif isinstance(val, StrEnum):
                result[column.key] = val.value
            else:
                result[column.key] = val
        return result

    def compute_etag(self) -> str:
        state_dict = self.to_dict()
        canonical = "|".join(f"{k}:{state_dict[k]}" for k in sorted(state_dict))
        digest = hashlib.sha256(
            f"{self.__resource_meta__.resource_name}:{canonical}".encode()
        ).hexdigest()[:16]
        return f'"{digest}"'


class ServiceModel(BaseResourceModel):
    __tablename__ = CollectionName.SERVICES.value
    __table_args__ = (
        CheckConstraint("length(trim(name)) >= 2", name="ck_services_name_len"),
        CheckConstraint("length(trim(slug)) >= 2", name="ck_services_slug_len"),
        CheckConstraint("length(trim(description)) >= 5", name="ck_services_desc_len"),
        CheckConstraint(
            "length(trim(owner_team)) >= 2", name="ck_services_owner_team_len"
        ),
    )

    __resource_meta__ = ResourceMetadata(
        resource_name=ResourceName.SERVICE,
        collection_name=CollectionName.SERVICES,
        id_param=PathParam.SERVICE_ID,
        detail_route=RouteName.SERVICE_DETAIL,
        collection_route=RouteName.SERVICES_LIST,
        create_route=RouteName.SERVICES_CREATE,
        replace_route=RouteName.SERVICE_REPLACE,
        patch_route=RouteName.SERVICE_PATCH,
        delete_route=RouteName.SERVICE_DELETE,
        delete_admin_only=True,
        title_field="name",
    )

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[ServiceTier] = mapped_column(
        _sa_str_enum(ServiceTier, "ck_services_tier"),
        nullable=False,
        default=ServiceTier.TIER_1,
    )
    owner_team: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    releases: Mapped[list["ReleaseModel"]] = relationship(
        "ReleaseModel", back_populates="service", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["IncidentModel"]] = relationship(
        "IncidentModel", back_populates="service", cascade="all, delete-orphan"
    )


class ReleaseModel(BaseResourceModel):
    __tablename__ = CollectionName.RELEASES.value
    __table_args__ = (
        CheckConstraint("length(trim(version)) >= 2", name="ck_releases_version_len"),
        CheckConstraint("length(trim(commit_sha)) >= 7", name="ck_releases_sha_len"),
        CheckConstraint(
            "length(trim(deployed_by)) >= 2", name="ck_releases_deployer_len"
        ),
    )

    __resource_meta__ = ResourceMetadata(
        resource_name=ResourceName.RELEASE,
        collection_name=CollectionName.RELEASES,
        id_param=PathParam.RELEASE_ID,
        detail_route=RouteName.RELEASE_DETAIL,
        collection_route=RouteName.SERVICE_RELEASES_LIST,
        create_route=RouteName.SERVICE_RELEASES_CREATE,
        patch_route=RouteName.RELEASE_PATCH,
        delete_route=RouteName.RELEASE_DELETE,
        parent_id_field="service_id",
        parent_id_param=PathParam.SERVICE_ID,
        owner_field="deployed_by",
        title_field="version",
    )

    service_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{CollectionName.SERVICES.value}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    environment: Mapped[ReleaseEnvironment] = mapped_column(
        _sa_str_enum(ReleaseEnvironment, "ck_releases_environment"),
        nullable=False,
        default=ReleaseEnvironment.PRODUCTION,
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployed_by: Mapped[str] = mapped_column(String(50), nullable=False)

    service: Mapped["ServiceModel"] = relationship(
        "ServiceModel", back_populates="releases"
    )
    incidents: Mapped[list["IncidentModel"]] = relationship(
        "IncidentModel", back_populates="release"
    )


class IncidentModel(BaseResourceModel):
    __tablename__ = CollectionName.INCIDENTS.value
    __table_args__ = (
        CheckConstraint("length(trim(title)) >= 3", name="ck_incidents_title_len"),
        CheckConstraint("length(trim(summary)) >= 5", name="ck_incidents_summary_len"),
        CheckConstraint(
            "length(trim(reported_by)) >= 2", name="ck_incidents_reporter_len"
        ),
    )

    __resource_meta__ = ResourceMetadata(
        resource_name=ResourceName.INCIDENT,
        collection_name=CollectionName.INCIDENTS,
        id_param=PathParam.INCIDENT_ID,
        detail_route=RouteName.INCIDENT_DETAIL,
        collection_route=RouteName.INCIDENTS_LIST,
        create_route=RouteName.INCIDENTS_CREATE,
        replace_route=RouteName.INCIDENT_REPLACE,
        patch_route=RouteName.INCIDENT_PATCH,
        delete_route=RouteName.INCIDENT_DELETE,
        parent_id_field="service_id",
        parent_id_param=PathParam.SERVICE_ID,
        owner_field="reported_by",
        title_field="title",
    )

    service_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{CollectionName.SERVICES.value}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    release_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(f"{CollectionName.RELEASES.value}.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        _sa_str_enum(IncidentSeverity, "ck_incidents_severity"),
        nullable=False,
        default=IncidentSeverity.MEDIUM,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        _sa_str_enum(IncidentStatus, "ck_incidents_status"),
        nullable=False,
        default=IncidentStatus.OPEN,
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[str] = mapped_column(String(50), nullable=False)

    service: Mapped["ServiceModel"] = relationship(
        "ServiceModel", back_populates="incidents"
    )
    release: Mapped["ReleaseModel | None"] = relationship(
        "ReleaseModel", back_populates="incidents"
    )


ALL_RESOURCE_MODELS: tuple[type[BaseResourceModel], ...] = (
    ServiceModel,
    ReleaseModel,
    IncidentModel,
)
