import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any

from litestar import Request, Response
from sqlalchemy import event, select

from app.core.enums import HttpHeader, HttpMethod, ResourceName
from app.core.exceptions import PreconditionFailedError
from app.db.base import async_session_factory
from app.db.models import ALL_RESOURCE_MODELS, BaseResourceModel
from app.security.guards import ensure_owner_or_admin


@dataclass(frozen=True)
class CachedResourceState:
    etag: str
    last_modified: datetime
    owner: str | None = None


class ResourceStateRegistry:
    """In-memory state registry synchronized with SQLAlchemy ORM lifecycle events."""

    def __init__(self) -> None:
        self._store: dict[tuple[ResourceName, int], CachedResourceState] = {}

    def record(self, instance: BaseResourceModel) -> CachedResourceState:
        meta = instance.__resource_meta__
        owner = getattr(instance, meta.owner_field, None) if meta.owner_field else None
        state = CachedResourceState(
            etag=instance.compute_etag(),
            last_modified=instance.updated_at,
            owner=owner,
        )
        if instance.id is not None:
            self._store[(meta.resource_name, int(instance.id))] = state
        return state

    def evict(self, instance: BaseResourceModel) -> None:
        meta = instance.__resource_meta__
        if instance.id is not None:
            self._store.pop((meta.resource_name, int(instance.id)), None)

    def get(
        self, resource_name: ResourceName, entity_id: int
    ) -> CachedResourceState | None:
        return self._store.get((resource_name, entity_id))


resource_state_registry = ResourceStateRegistry()


# Automatically keep the registry synchronized with database mutations
for _model_cls in ALL_RESOURCE_MODELS:
    event.listen(
        _model_cls,
        "after_insert",
        lambda _mapper, _conn, target: resource_state_registry.record(target),
    )
    event.listen(
        _model_cls,
        "after_update",
        lambda _mapper, _conn, target: resource_state_registry.record(target),
    )
    event.listen(
        _model_cls,
        "after_delete",
        lambda _mapper, _conn, target: resource_state_registry.evict(target),
    )


async def warm_up_cache_registry() -> None:
    """Populates the ETag registry on application startup from persisted records."""
    async with async_session_factory() as session:
        for model_cls in ALL_RESOURCE_MODELS:
            records = (await session.scalars(select(model_cls))).all()
            for record in records:
                resource_state_registry.record(record)


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
        HttpHeader.CACHE_CONTROL.value: f"{directive}, max-age={max_age}, must-revalidate",
        HttpHeader.ETAG.value: etag,
    }
    if last_modified is not None:
        headers[HttpHeader.LAST_MODIFIED.value] = format_http_date(last_modified)
    return headers


def evaluate_conditional_get(
    request: Request,
    etag: str,
    last_modified: datetime | None = None,
    is_private: bool = False,
) -> Response | None:
    """Returns a 304 Not Modified response if If-None-Match or If-Modified-Since matches."""
    if request.method not in (HttpMethod.GET, HttpMethod.HEAD):
        return None

    headers = build_cache_headers(
        etag=etag, last_modified=last_modified, is_private=is_private
    )
    if_none_match = request.headers.get(HttpHeader.IF_NONE_MATCH.lower())

    if if_none_match:
        client_tags = [tag.strip() for tag in if_none_match.split(",")]
        if "*" in client_tags or etag in client_tags:
            return Response(content=b"", status_code=304, headers=headers)
        return None

    if_modified_since = request.headers.get(HttpHeader.IF_MODIFIED_SINCE.lower())
    if if_modified_since and last_modified is not None:
        since_dt = parse_http_date(if_modified_since)
        resource_dt = last_modified.astimezone(UTC).replace(microsecond=0)
        if since_dt is not None and resource_dt <= since_dt:
            return Response(content=b"", status_code=304, headers=headers)

    return None


def verify_if_match(request: Request, current_etag: str) -> None:
    """Evaluates If-Match header for optimistic concurrency control (412 Precondition Failed)."""
    if_match = request.headers.get(HttpHeader.IF_MATCH.lower())
    if not if_match:
        return

    client_tags = [tag.strip() for tag in if_match.split(",")]
    if "*" not in client_tags and current_etag not in client_tags:
        raise PreconditionFailedError(
            current_etag=current_etag, provided_if_match=if_match
        )


async def early_conditional_request_hook(request: Request) -> Response | None:
    """Executes after route guards but BEFORE controller and DB session creation.

    Short-circuits unmodified GET/HEAD requests with 304 Not Modified and rejects
    stale PUT/PATCH/DELETE requests with 412 Precondition Failed.
    """
    handler_name = request.route_handler.name
    if not handler_name:
        return None

    logical_route_name = handler_name.split(":", 1)[-1]

    for model_cls in ALL_RESOURCE_MODELS:
        meta = model_cls.__resource_meta__
        raw_id = request.path_params.get(meta.id_param.value)
        if raw_id is None:
            continue

        try:
            entity_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        state = resource_state_registry.get(meta.resource_name, entity_id)
        if state is None:
            return None

        if logical_route_name == meta.detail_route.value:
            return evaluate_conditional_get(
                request,
                etag=state.etag,
                last_modified=state.last_modified,
            )

        mutation_routes = {
            r.value
            for r in (meta.replace_route, meta.patch_route, meta.delete_route)
            if r is not None
        }
        if logical_route_name in mutation_routes:
            if meta.owner_field and state.owner is not None:
                ensure_owner_or_admin(request.scope.get("user"), state.owner)
            verify_if_match(request, state.etag)
            return None

    return None
