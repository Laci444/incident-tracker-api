import msgspec

from app.core.enums import ReleaseEnvironment
from app.schemas.common import (
    CommitShaStr,
    HALLinksMap,
    MergePatchBase,
    VersionStr,
)


class ReleaseCreate(msgspec.Struct, kw_only=True):
    version: VersionStr
    commit_sha: CommitShaStr
    environment: ReleaseEnvironment = ReleaseEnvironment.PRODUCTION
    release_notes: str | None = None


class ReleasePatch(MergePatchBase, kw_only=True):
    version: VersionStr | msgspec.UnsetType = msgspec.UNSET
    commit_sha: CommitShaStr | msgspec.UnsetType = msgspec.UNSET
    environment: ReleaseEnvironment | msgspec.UnsetType = msgspec.UNSET
    release_notes: str | None | msgspec.UnsetType = msgspec.UNSET


class ReleaseResponseDTO(msgspec.Struct, kw_only=True):
    id: int
    service_id: int
    version: str
    commit_sha: str
    environment: ReleaseEnvironment
    release_notes: str | None
    deployed_by: str
    created_at: str
    updated_at: str
    _links: HALLinksMap


class EmbeddedReleasesDTO(msgspec.Struct, kw_only=True):
    releases: list[ReleaseResponseDTO]


class ReleaseCollectionResponseDTO(msgspec.Struct, kw_only=True):
    service_id: int
    service_name: str
    total: int
    count: int
    limit: int
    offset: int
    _links: HALLinksMap
    _embedded: EmbeddedReleasesDTO
