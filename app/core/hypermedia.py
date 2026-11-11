from typing import Any

from litestar import Response


def hal_link(
    href: str,
    title: str | None = None,
    method: str | None = None,
    media_type: str | None = None,
) -> dict[str, str]:
    link: dict[str, str] = {"href": href}
    if title:
        link["title"] = title
    if method:
        link["method"] = method
    if media_type:
        link["type"] = media_type
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
        "Allow": ", ".join(allowed_methods),
        "Cache-Control": "public, max-age=3600",
    }
    if supports_merge_patch or "PATCH" in allowed_methods:
        headers["Accept-Patch"] = "application/merge-patch+json"

    return Response(content=b"", status_code=204, headers=headers)
