import hashlib
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class ServiceModel(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="tier-1")
    owner_team: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    releases: Mapped[list["ReleaseModel"]] = relationship(
        "ReleaseModel", back_populates="service", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["IncidentModel"]] = relationship(
        "IncidentModel", back_populates="service", cascade="all, delete-orphan"
    )

    def compute_etag(self) -> str:
        payload = f"service:{self.id}:{self.name}:{self.slug}:{self.tier}:{self.is_active}:{self.updated_at.isoformat()}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f'"{digest}"'


class ReleaseModel(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    environment: Mapped[str] = mapped_column(String(30), nullable=False, default="production")
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployed_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    service: Mapped["ServiceModel"] = relationship("ServiceModel", back_populates="releases")
    incidents: Mapped[list["IncidentModel"]] = relationship("IncidentModel", back_populates="release")

    def compute_etag(self) -> str:
        payload = f"release:{self.id}:{self.service_id}:{self.version}:{self.environment}:{self.updated_at.isoformat()}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f'"{digest}"'


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable FK allows linking/unlinking a suspect release via RFC 7396 JSON Merge Patch
    release_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("releases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    service: Mapped["ServiceModel"] = relationship("ServiceModel", back_populates="incidents")
    release: Mapped["ReleaseModel | None"] = relationship("ReleaseModel", back_populates="incidents")

    def compute_etag(self) -> str:
        payload = (
            f"incident:{self.id}:{self.service_id}:{self.release_id}:"
            f"{self.severity}:{self.status}:{self.updated_at.isoformat()}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f'"{digest}"'
