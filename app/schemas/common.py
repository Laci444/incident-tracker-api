from typing import Any, TypeVar

import msgspec
from litestar import Request

from app.core.exceptions import ProblemException

T = TypeVar("T")

ALLOWED_TIERS = {"tier-1", "tier-2", "tier-3"}
ALLOWED_ENVIRONMENTS = {"production", "staging", "development"}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
ALLOWED_STATUSES = {"open", "mitigated", "resolved"}


async def parse_merge_patch_body(request: Request, schema_type: type[T]) -> T:
    """Decodes and validates an RFC 7396 JSON Merge Patch body while preserving UNSET vs null."""
    raw_body = await request.body()
    if not raw_body:
        raise ProblemException(
            status_code=400,
            title="Bad Request",
            detail="Request body cannot be empty for JSON Merge Patch.",
            type_slug="empty-patch-body",
        )

    try:
        raw_obj = msgspec.json.decode(raw_body)
    except msgspec.DecodeError as exc:
        raise ProblemException(
            status_code=400,
            title="Malformed JSON",
            detail=f"Invalid JSON payload: {exc}",
            type_slug="malformed-json",
        ) from exc

    # RFC 7396 requires the patch document to be a JSON object when patching an object resource
    if not isinstance(raw_obj, dict):
        raise ProblemException(
            status_code=422,
            title="Unprocessable Content",
            detail="JSON Merge Patch payload for a resource must be a JSON object.",
            type_slug="invalid-merge-patch-object",
        )

    try:
        return msgspec.convert(raw_obj, type=schema_type, strict=True)
    except msgspec.ValidationError as exc:
        raise ProblemException(
            status_code=422,
            title="Unprocessable Content",
            detail=str(exc),
            type_slug="patch-validation-error",
        ) from exc


def merge_patch_openapi_body(example: dict[str, Any]) -> dict[str, Any]:
    """Generates OpenAPI requestBody metadata for RFC 7396 application/merge-patch+json."""
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/merge-patch+json": {
                    "schema": {"type": "object"},
                    "example": example,
                }
            },
        }
    }
