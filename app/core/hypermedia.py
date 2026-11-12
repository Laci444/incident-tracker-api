from dataclasses import dataclass
from typing import Any

from litestar import Request, Response
from litestar.exceptions import NoRouteMatchFoundException
from sqlalchemy import inspect

from app.core.enums import (
    ApiPath,
    ApiVersion,
    HttpHeader,
    HttpMethod,
    LinkRel,
    MediaType,
    ResourceName,
    RouteName,
    UserRole,
)
from app.db.models import ALL_RESOURCE_MODELS, BaseResourceModel
from app.repositories.base import PageResult
from app.security.auth import AuthenticatedUser

_MODEL_BY_FK_FIELD: dict[str, type[BaseResourceModel]] = {
    f"{m.__resource_meta__.resource_name.value}_id": m for m in ALL_RESOURCE_MODELS
}


@dataclass(frozen=True)
class DomainPayload:
    """Wrapper for non-ORM domain responses (Discovery root, Version index, User profile)."""

    data: dict[str, Any]
    links: dict[str, Any]
    xml_root: ResourceName
    is_private: bool = False
    max_age: int = 60


def hal_link(
    href: str,
    title: str | None = None,
    method: HttpMethod | str | None = None,
    media_type: MediaType | str | None = None,
) -> dict[str, str]:
    link: dict[str, str] = {"href": href}
    if title:
        link["title"] = title
    if method:
        link["method"] = str(method)
    if media_type:
        link["type"] = str(media_type)
    return link


def format_rfc8288_link_header(links: dict[str, Any]) -> str:
    """Serializes a HAL _links dictionary into an RFC 8288 HTTP Link header string."""
    entries: list[str] = []
    for rel, target in links.items():
        targets = target if isinstance(target, list) else [target]
        for item in targets:
            href = item.get("href")
            if not href:
                continue
            parts = [f"<{href}>", f'rel="{rel}"']
            if "title" in item:
                parts.append(f'title="{item["title"]}"')
            if "type" in item:
                parts.append(f'type="{item["type"]}"')
            entries.append("; ".join(parts))
    return ", ".join(entries)


def build_options_response(
    allowed_methods: list[str],
    supports_merge_patch: bool = False,
) -> Response:
    headers = {
        HttpHeader.ALLOW.value: ", ".join(allowed_methods),
        HttpHeader.CACHE_CONTROL.value: "public, max-age=3600",
    }
    if supports_merge_patch or HttpMethod.PATCH.value in allowed_methods:
        headers[HttpHeader.ACCEPT_PATCH.value] = MediaType.MERGE_PATCH_JSON.value

    return Response(content=b"", status_code=204, headers=headers)


class HypermediaAssembler:
    """Dynamically builds HAL representations from model metadata and SQLAlchemy relationships."""

    def __init__(
        self, request: Request, version: ApiVersion = ApiVersion.CURRENT
    ) -> None:
        self.request = request
        self.version = version
        self.user: AuthenticatedUser | None = request.scope.get("user")

    def resolve_url(self, route_name: RouteName, **path_params: Any) -> str:
        for candidate in (route_name.versioned(self.version), route_name.value):
            try:
                return self.request.app.route_reverse(candidate, **path_params)
            except NoRouteMatchFoundException:
                if path_params:
                    try:
                        base_url = self.request.app.route_reverse(candidate)
                        query = "&".join(f"{k}={v}" for k, v in path_params.items())
                        return f"{base_url}?{query}"
                    except NoRouteMatchFoundException:
                        continue
        return ApiPath.ROOT.value

    def serialize_model(self, instance: BaseResourceModel) -> dict[str, Any]:
        meta = instance.__resource_meta__
        data = instance.to_dict()
        title = str(getattr(instance, meta.title_field, meta.resource_name.value))

        self_uri = self.resolve_url(
            meta.detail_route, **{meta.id_param.value: instance.id}
        )

        if meta.parent_id_field and meta.parent_id_param:
            parent_id = getattr(instance, meta.parent_id_field)
            collection_uri = self.resolve_url(
                meta.collection_route, **{meta.parent_id_param.value: parent_id}
            )
        else:
            collection_uri = self.resolve_url(meta.collection_route)

        links: dict[str, Any] = {
            LinkRel.SELF.value: hal_link(self_uri, title=title),
            LinkRel.COLLECTION.value: hal_link(
                collection_uri, title=f"All {meta.collection_name.value.capitalize()}"
            ),
            LinkRel.DESCRIBEDBY.value: hal_link(
                ApiPath.OPENAPI_JSON.value, title="OpenAPI Specification"
            ),
        }

        if meta.parent_id_field is None:
            links[LinkRel.UP.value] = hal_link(
                self.resolve_url(RouteName.VERSION_ROOT), title="Version Entry Point"
            )

        # Dynamically inspect SQLAlchemy relationships to generate links without magic strings
        mapper = inspect(instance.__class__)
        for rel in mapper.relationships:
            target_cls = rel.mapper.class_
            if not issubclass(target_cls, BaseResourceModel):
                continue
            target_meta = target_cls.__resource_meta__

            if rel.uselist:
                # One-to-Many child collection relationship
                rel_key = target_meta.collection_name.value
                if target_meta.parent_id_param == meta.id_param:
                    try:
                        child_uri = self.resolve_url(
                            target_meta.collection_route,
                            **{meta.id_param.value: instance.id},
                        )
                    except Exception:
                        base_col = self.resolve_url(target_meta.collection_route)
                        child_uri = f"{base_col}?{meta.id_param.value}={instance.id}"
                else:
                    base_col = self.resolve_url(target_meta.collection_route)
                    filter_param = (
                        meta.parent_id_param.value
                        if meta.parent_id_param
                        else meta.id_param.value
                    )
                    filter_val = (
                        getattr(instance, meta.parent_id_field)
                        if meta.parent_id_field
                        else instance.id
                    )
                    child_uri = f"{base_col}?{filter_param}={filter_val}"

                links[rel_key] = hal_link(
                    child_uri,
                    title=f"{target_meta.collection_name.value.capitalize()} for {title}",
                )
                if (
                    meta.parent_id_field is not None
                    and LinkRel.RELATED.value not in links
                ):
                    links[LinkRel.RELATED.value] = links[rel_key]
            else:
                # Many-to-One parent or associated entity relationship
                fk_col = next(iter(rel.local_columns)).key
                fk_val = getattr(instance, fk_col)
                if fk_val is None:
                    continue

                target_uri = self.resolve_url(
                    target_meta.detail_route, **{target_meta.id_param.value: fk_val}
                )
                target_label = target_meta.resource_name.value.capitalize()
                links[target_meta.resource_name.value] = hal_link(
                    target_uri, title=f"Associated {target_label}"
                )

                if fk_col == meta.parent_id_field:
                    links[LinkRel.UP.value] = hal_link(
                        target_uri, title=f"Parent {target_label}"
                    )
                else:
                    links[LinkRel.RELATED.value] = hal_link(
                        target_uri, title=f"Related {target_label}"
                    )

        # Author link if current user owns the resource
        if meta.owner_field and self.user:
            owner_username = getattr(instance, meta.owner_field)
            if self.user.username == owner_username:
                links[LinkRel.AUTHOR.value] = hal_link(
                    self.resolve_url(RouteName.ME),
                    title=f"Author ({owner_username})",
                )

        # State-transition links (edit / delete) filtered by role and ownership
        if self._can_edit(instance):
            links[LinkRel.EDIT.value] = hal_link(
                self_uri,
                title=f"Modify {meta.resource_name.value.capitalize()}",
                method=HttpMethod.PATCH,
            )
        if self._can_delete(instance):
            links[LinkRel.DELETE.value] = hal_link(
                self_uri,
                title=f"Delete {meta.resource_name.value.capitalize()}",
                method=HttpMethod.DELETE,
            )

        data["_links"] = links
        return data

    def serialize_page(self, page: PageResult[BaseResourceModel]) -> dict[str, Any]:
        meta = page.model_cls.__resource_meta__
        collection_key = meta.collection_name.value
        base_uri = self.resolve_url(page.collection_route, **page.route_params)

        embedded_items = [self.serialize_model(item) for item in page.items]

        if meta.parent_id_param and meta.parent_id_param.value in page.route_params:
            parent_param = meta.parent_id_param.value
            parent_model = _MODEL_BY_FK_FIELD.get(parent_param)
            if parent_model:
                up_uri = self.resolve_url(
                    parent_model.__resource_meta__.detail_route,
                    **{parent_param: page.route_params[parent_param]},
                )
            else:
                up_uri = self.resolve_url(RouteName.VERSION_ROOT)
        else:
            up_uri = self.resolve_url(RouteName.VERSION_ROOT)

        links: dict[str, Any] = {
            LinkRel.SELF.value: hal_link(
                f"{base_uri}?limit={page.limit}&offset={page.offset}",
                title=f"{collection_key.capitalize()} Collection",
            ),
            LinkRel.UP.value: hal_link(up_uri, title="Parent Resource"),
            LinkRel.FIRST.value: hal_link(
                f"{base_uri}?limit={page.limit}&offset=0",
                title="First Page",
            ),
            LinkRel.ITEM.value: [
                hal_link(
                    self.resolve_url(
                        meta.detail_route, **{meta.id_param.value: item.id}
                    ),
                    title=str(getattr(item, meta.title_field, item.id)),
                )
                for item in page.items
            ],
            LinkRel.DESCRIBEDBY.value: hal_link(
                ApiPath.OPENAPI_JSON.value, title="OpenAPI Specification"
            ),
        }

        if page.offset + page.limit < page.total:
            links[LinkRel.NEXT.value] = hal_link(
                f"{base_uri}?limit={page.limit}&offset={page.offset + page.limit}",
                title="Next Page",
            )
        if page.offset > 0:
            prev_offset = max(0, page.offset - page.limit)
            links[LinkRel.PREV.value] = hal_link(
                f"{base_uri}?limit={page.limit}&offset={prev_offset}",
                title="Previous Page",
            )

        if (
            page.create_route
            and self.user
            and self.user.role in (UserRole.ADMIN, UserRole.DEVELOPER)
        ):
            create_uri = self.resolve_url(page.create_route, **page.route_params)
            links[LinkRel.CREATE_FORM.value] = hal_link(
                create_uri,
                title=f"Create {meta.resource_name.value.capitalize()}",
                method=HttpMethod.POST,
            )

        payload: dict[str, Any] = {
            **page.extra_metadata,
            "total": page.total,
            "count": len(embedded_items),
            "limit": page.limit,
            "offset": page.offset,
            "_links": links,
            "_embedded": {collection_key: embedded_items},
        }
        return payload

    def _can_edit(self, instance: BaseResourceModel) -> bool:
        if self.user is None:
            return False
        if self.user.role == UserRole.ADMIN:
            return True
        if self.user.role == UserRole.DEVELOPER:
            meta = instance.__resource_meta__
            if meta.owner_field is None:
                return True
            return getattr(instance, meta.owner_field) == self.user.username
        return False

    def _can_delete(self, instance: BaseResourceModel) -> bool:
        if self.user is None:
            return False
        meta = instance.__resource_meta__
        if meta.delete_admin_only:
            return self.user.role == UserRole.ADMIN
        return self._can_edit(instance)
