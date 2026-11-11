import hashlib
import json
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any

from litestar import Request, Response

from app.core.exceptions import ProblemException


def format_http_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return format_datetime(dt.astimezone(UTC), usegmt=True)


def parse_http_date(header_val: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(header_val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).replace(microsecond=0)
    except (TypeError, ValueError):
        return None


def compute_payload_etag(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()[:16]
    return f'"{digest}"'


def build_cache_headers(
    etag: str,
    last_modified: datetime | None = None,
    max_age: int = 60,
    is_private: bool = False,
) -> dict[str, str]:
    directive = "private" if is_private else "public"
    headers = {
        "Cache-Control": f"{directive}, max-age={max_age}, must-revalidate",
        "ETag": etag,
    }
    if last_modified is not None:
        headers["Last-Modified"] = format_http_date(last_modified)
    return headers


def evaluate_conditional_get(
    request: Request,
    etag: str,
    last_modified: datetime | None = None,
    is_private: bool = False,
) -> Response | None:
    """Returns a 304 Not Modified response if If-None-Match or If-Modified-Since matches."""
    if request.method not in ("GET", "HEAD"):
        return None

    headers = build_cache_headers(
        etag=etag, last_modified=last_modified, is_private=is_private
    )
    if_none_match = request.headers.get("if-none-match")

    if if_none_match:
        client_tags = [tag.strip() for tag in if_none_match.split(",")]
        if "*" in client_tags or etag in client_tags:
            return Response(content=b"", status_code=304, headers=headers)
        return None

    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since and last_modified is not None:
        since_dt = parse_http_date(if_modified_since)
        resource_dt = last_modified.astimezone(UTC).replace(microsecond=0)
        if since_dt is not None and resource_dt <= since_dt:
            return Response(content=b"", status_code=304, headers=headers)

    return None


def verify_if_match(request: Request, current_etag: str) -> None:
    """Evaluates If-Match header for optimistic concurrency control (412 Precondition Failed)."""
    if_match = request.headers.get("if-match")
    if not if_match:
        return

    client_tags = [tag.strip() for tag in if_match.split(",")]
    if "*" not in client_tags and current_etag not in client_tags:
        raise ProblemException(
            status_code=412,
            title="Precondition Failed",
            detail=f"Resource ETag {current_etag} does not match If-Match header ({if_match}).",
            type_slug="precondition-failed",
            headers={"ETag": current_etag},
        )
