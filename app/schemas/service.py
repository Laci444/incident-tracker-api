import msgspec

from app.core.enums import ServiceTier
from app.schemas.common import (
    DescriptionStr,
    HALLinksMap,
    MergePatchBase,
    ShortNameStr,
    SlugStr,
)


class ServiceCreate(msgspec.Struct, kw_only=True):
    name: ShortNameStr
    slug: SlugStr
    description: DescriptionStr
    owner_team: ShortNameStr
    tier: ServiceTier = ServiceTier.TIER_1
    is_active: bool = True


class ServiceUpdate(msgspec.Struct, kw_only=True):
    name: ShortNameStr
    slug: SlugStr
    description: DescriptionStr
    owner_team: ShortNameStr
    tier: ServiceTier
    is_active: bool


class ServicePatch(MergePatchBase, kw_only=True):
    __nullable_fields__ = frozenset()
    __lowercase_fields__ = frozenset({"slug"})

    name: ShortNameStr | None | msgspec.UnsetType = msgspec.UNSET
    slug: SlugStr | None | msgspec.UnsetType = msgspec.UNSET
    description: DescriptionStr | None | msgspec.UnsetType = msgspec.UNSET
    owner_team: ShortNameStr | None | msgspec.UnsetType = msgspec.UNSET
    tier: ServiceTier | None | msgspec.UnsetType = msgspec.UNSET
    is_active: bool | None | msgspec.UnsetType = msgspec.UNSET


class ServiceResponseDTO(msgspec.Struct, kw_only=True):
    id: int
    name: str
    slug: str
    description: str
    tier: ServiceTier
    owner_team: str
    is_active: bool
    created_at: str
    updated_at: str
    _links: HALLinksMap


class EmbeddedServicesDTO(msgspec.Struct, kw_only=True):
    services: list[ServiceResponseDTO]


class ServiceCollectionResponseDTO(msgspec.Struct, kw_only=True):
    total: int
    count: int
    limit: int
    offset: int
    _links: HALLinksMap
    _embedded: EmbeddedServicesDTO
