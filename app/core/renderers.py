import json
from contextvars import ContextVar
from typing import Any

from dicttoxml2 import dicttoxml
from litestar import Request, Response

from app.core.caching import (
    build_cache_headers,
    compute_payload_etag,
    evaluate_conditional_get,
    resource_state_registry,
)
from app.core.enums import HttpHeader, HttpMethod, LinkRel, MediaType
from app.core.exceptions import NotAcceptableError
from app.core.hypermedia import (
    DomainPayload,
    HypermediaAssembler,
    format_rfc8288_link_header,
)
from app.db.models import BaseResourceModel
from app.repositories.base import PageResult

current_request_var: ContextVar[Request | None] = ContextVar(
    "current_request_var", default=None
)

SUPPORTED_MEDIA_TYPES: tuple[MediaType, ...] = (
    MediaType.HAL_JSON,
    MediaType.JSON,
    MediaType.XML,
    MediaType.TEXT_XML,
    MediaType.PROBLEM_JSON,
    MediaType.PROBLEM_XML,
)


def negotiate_media_type(request: Request) -> str:
    accept_header = request.headers.get(
        HttpHeader.ACCEPT.lower(), MediaType.WILDCARD.value
    ).strip()
    if not accept_header or accept_header == MediaType.WILDCARD.value:
        return MediaType.HAL_JSON.value

    candidates: list[tuple[float, str]] = []
    for raw_part in accept_header.split(","):
        segments = [s.strip() for s in raw_part.split(";") if s.strip()]
        if not segments:
            continue
        mime = segments[0].lower()
        q = 1.0
        for param in segments[1:]:
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        if q > 0:
            candidates.append((q, mime))

    candidates.sort(key=lambda item: item[0], reverse=True)

    supported_values = {m.value for m in SUPPORTED_MEDIA_TYPES}
    for _, mime in candidates:
        if mime in (MediaType.WILDCARD.value, MediaType.APP_WILDCARD.value):
            return MediaType.HAL_JSON.value
        if mime in supported_values:
            if mime in (MediaType.TEXT_XML.value, MediaType.PROBLEM_XML.value):
                return MediaType.XML.value
            if mime == MediaType.PROBLEM_JSON.value:
                return MediaType.HAL_JSON.value
            return mime

    raise NotAcceptableError(
        accept_header=accept_header,
        supported_types=[
            MediaType.HAL_JSON.value,
            MediaType.JSON.value,
            MediaType.XML.value,
        ],
    )


class HalNegotiatedResponse(Response):
    """Presentation layer Response class separating HTTP/HAL formatting from controllers."""

    def __init__(self, content: Any = None, **kwargs: Any) -> None:
        request = current_request_var.get()
        status_code: int = kwargs.get("status_code") or 200
        headers: dict[str, str] = dict(kwargs.get("headers") or {})

        if request is not None and isinstance(
            content, (BaseResourceModel, PageResult, DomainPayload)
        ):
            assembler = HypermediaAssembler(request)

            if isinstance(content, BaseResourceModel):
                state = resource_state_registry.record(content)
                payload = assembler.serialize_model(content)
                etag = state.etag
                last_modified = state.last_modified
                max_age = 60
                is_private = False
                xml_root = content.__resource_meta__.resource_name.value

                if status_code == 201:
                    headers[HttpHeader.LOCATION.value] = payload["_links"][
                        LinkRel.SELF.value
                    ]["href"]

            elif isinstance(content, PageResult):
                payload = assembler.serialize_page(content)
                etag = compute_payload_etag(payload)
                last_modified = None
                max_age = 30
                is_private = False
                xml_root = content.model_cls.__resource_meta__.collection_name.value

            else:
                payload = {**content.data, "_links": content.links}
                etag = compute_payload_etag(payload)
                last_modified = None
                max_age = content.max_age
                is_private = content.is_private
                xml_root = content.xml_root.value

            cond_response = evaluate_conditional_get(
                request,
                etag=etag,
                last_modified=last_modified,
                is_private=is_private,
            )
            if cond_response is not None:
                kwargs["status_code"] = 304
                kwargs["headers"] = {**headers, **cond_response.headers}
                super().__init__(content=b"", **kwargs)
                return

            cache_headers = build_cache_headers(
                etag=etag,
                last_modified=last_modified,
                max_age=max_age,
                is_private=is_private,
            )
            headers.update(cache_headers)
            headers[HttpHeader.LINK.value] = format_rfc8288_link_header(
                payload["_links"]
            )
            headers.setdefault(
                HttpHeader.VARY.value,
                f"{HttpHeader.ACCEPT.value}, {HttpHeader.AUTHORIZATION.value}",
            )

            media_type = negotiate_media_type(request)
            if media_type == MediaType.XML.value:
                body_bytes = dicttoxml(payload, custom_root=xml_root, attr_type=False)
            else:
                body_bytes = json.dumps(payload).encode("utf-8")

            if request.method == HttpMethod.HEAD.value:
                headers[HttpHeader.CONTENT_LENGTH.value] = str(len(body_bytes))
                body_bytes = b""

            kwargs["media_type"] = media_type
            kwargs["headers"] = headers
            super().__init__(content=body_bytes, **kwargs)
            return

        super().__init__(content=content, **kwargs)
