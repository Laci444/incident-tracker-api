import msgspec

from app.core.enums import IncidentSeverity, IncidentStatus
from app.schemas.common import (
    DescriptionStr,
    HALLinksMap,
    MergePatchBase,
    PositiveId,
    TitleStr,
)


class IncidentCreate(msgspec.Struct, kw_only=True):
    service_id: PositiveId
    title: TitleStr
    summary: DescriptionStr
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.OPEN
    release_id: PositiveId | None = None
    resolution_notes: str | None = None


class IncidentUpdate(msgspec.Struct, kw_only=True):
    service_id: PositiveId
    release_id: PositiveId | None
    title: TitleStr
    summary: DescriptionStr
    severity: IncidentSeverity
    status: IncidentStatus
    resolution_notes: str | None


class IncidentPatch(MergePatchBase, kw_only=True):
    service_id: PositiveId | msgspec.UnsetType = msgspec.UNSET
    release_id: PositiveId | None | msgspec.UnsetType = msgspec.UNSET
    title: TitleStr | msgspec.UnsetType = msgspec.UNSET
    summary: DescriptionStr | msgspec.UnsetType = msgspec.UNSET
    severity: IncidentSeverity | msgspec.UnsetType = msgspec.UNSET
    status: IncidentStatus | msgspec.UnsetType = msgspec.UNSET
    resolution_notes: str | None | msgspec.UnsetType = msgspec.UNSET


class IncidentResponseDTO(msgspec.Struct, kw_only=True):
    id: int
    service_id: int
    release_id: int | None
    title: str
    summary: str
    severity: IncidentSeverity
    status: IncidentStatus
    resolution_notes: str | None
    reported_by: str
    created_at: str
    updated_at: str
    _links: HALLinksMap


class EmbeddedIncidentsDTO(msgspec.Struct, kw_only=True):
    incidents: list[IncidentResponseDTO]


class IncidentCollectionResponseDTO(msgspec.Struct, kw_only=True):
    total: int
    count: int
    limit: int
    offset: int
    _links: HALLinksMap
    _embedded: EmbeddedIncidentsDTO
