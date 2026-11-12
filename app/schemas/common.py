from typing import Annotated, Any, ClassVar, TypeVar

import msgspec
from litestar.params import Body

from app.core.enums import MediaType, UserRole
from app.core.openapi import HALLinkDTO

PatchT = TypeVar("PatchT", bound="MergePatchBase")
MergePatchBody = Annotated[PatchT, Body(media_type=MediaType.MERGE_PATCH_JSON.value)]

# Reusable constrained scalar types for automatic validation before controller execution
ShortNameStr = Annotated[str, msgspec.Meta(min_length=2, max_length=100)]
SlugStr = Annotated[
    str,
    msgspec.Meta(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
]
TitleStr = Annotated[str, msgspec.Meta(min_length=3, max_length=150)]
DescriptionStr = Annotated[str, msgspec.Meta(min_length=5, max_length=2000)]
VersionStr = Annotated[str, msgspec.Meta(min_length=2, max_length=40)]
CommitShaStr = Annotated[
    str,
    msgspec.Meta(min_length=7, max_length=40, pattern=r"^[0-9a-fA-F]{7,40}$"),
]
PositiveId = Annotated[int, msgspec.Meta(ge=1)]
PageLimit = Annotated[int, msgspec.Meta(ge=1, le=50)]
PageOffset = Annotated[int, msgspec.Meta(ge=0)]

HALLinksMap = dict[str, HALLinkDTO | list[HALLinkDTO]]


class MergePatchBase(msgspec.Struct, kw_only=True):
    """Base schema for RFC 7396 JSON Merge Patch payloads."""

    __nullable_fields__: ClassVar[frozenset[str]] = frozenset()
    __lowercase_fields__: ClassVar[frozenset[str]] = frozenset()

    def extract_changes(self) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self.__struct_fields__:
            val = getattr(self, field_name)
            if val is msgspec.UNSET:
                continue
            if isinstance(val, str):
                val = val.strip()
                if field_name in self.__lowercase_fields__:
                    val = val.lower()
            changes[field_name] = val
        return changes


class ApiDiscoveryResponseDTO(msgspec.Struct, kw_only=True):
    """OpenAPI schema for the version-agnostic /api discovery endpoint."""

    api_name: str
    current_version: str
    supported_versions: list[str]
    rmm_level: int = 3
    _links: HALLinksMap


class VersionIndexResponseDTO(msgspec.Struct, kw_only=True):
    """OpenAPI schema for the versioned /api/v1 entry point."""

    api_name: str
    version: str
    rmm_level: int = 3
    authenticated_as: str | None = None
    _links: HALLinksMap


class UserProfileResponseDTO(msgspec.Struct, kw_only=True):
    """OpenAPI schema for the /api/v1/me authenticated user profile resource."""

    username: str
    display_name: str
    role: UserRole
    permissions: list[str]
    _links: HALLinksMap
