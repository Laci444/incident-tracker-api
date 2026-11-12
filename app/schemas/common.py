from typing import Annotated, Any, ClassVar, TypeVar

import msgspec

from app.core.enums import UserRole
from app.core.exceptions import BadRequestError, ValidationFailedError
from app.core.openapi import HALLinkDTO

PatchT = TypeVar("PatchT", bound="MergePatchBase")

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
    """Base schema for RFC 7396 JSON Merge Patch payloads with built-in nullability validation."""

    __nullable_fields__: ClassVar[frozenset[str]] = frozenset()
    __lowercase_fields__: ClassVar[frozenset[str]] = frozenset()

    def extract_changes(self) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self.__struct_fields__:
            val = getattr(self, field_name)
            if val is msgspec.UNSET:
                continue
            if val is None and field_name not in self.__nullable_fields__:
                raise ValidationFailedError(
                    f"Field '{field_name}' is non-nullable and cannot be cleared via null in JSON Merge Patch."
                )
            if isinstance(val, str):
                val = val.strip()
                if field_name in self.__lowercase_fields__:
                    val = val.lower()
            changes[field_name] = val
        return changes


def decode_merge_patch(raw_body: bytes, schema_type: type[PatchT]) -> dict[str, Any]:
    """Decodes an RFC 7396 application/merge-patch+json body and returns validated field changes."""
    if not raw_body:
        raise BadRequestError("Request body cannot be empty for JSON Merge Patch.")

    try:
        decoded_json = msgspec.json.decode(raw_body)
    except msgspec.DecodeError as exc:
        raise BadRequestError(f"Malformed JSON payload: {exc}") from exc

    if not isinstance(decoded_json, dict):
        raise ValidationFailedError(
            "JSON Merge Patch payload for a resource must be a JSON object."
        )

    try:
        patch_struct = msgspec.convert(decoded_json, type=schema_type, strict=True)
    except msgspec.ValidationError as exc:
        raise ValidationFailedError(str(exc)) from exc

    return patch_struct.extract_changes()


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
