from litestar.connection import ASGIConnection
from litestar.handlers.base import BaseRouteHandler

from app.core.exceptions import ProblemException
from app.security.auth import AuthenticatedUser


def require_authenticated(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    if connection.scope.get("user") is None:
        raise ProblemException(
            status_code=401,
            title="Authentication Required",
            detail="You must provide valid HTTP Basic credentials to access this resource.",
            type_slug="authentication-required",
        )


def require_writer(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None:
    require_authenticated(connection, route_handler)
    user: AuthenticatedUser = connection.user
    if user.role not in ("admin", "developer"):
        raise ProblemException(
            status_code=403,
            title="Forbidden",
            detail=f"User '{user.username}' with role '{user.role}' has read-only access.",
            type_slug="insufficient-permissions",
        )


def require_admin(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None:
    require_authenticated(connection, route_handler)
    user: AuthenticatedUser = connection.user
    if user.role != "admin":
        raise ProblemException(
            status_code=403,
            title="Forbidden",
            detail="Only users with the 'admin' role may perform this operation.",
            type_slug="admin-required",
        )


def ensure_owner_or_admin(user: AuthenticatedUser | None, owner_username: str) -> None:
    """Enforces resource-level authorization: developers can only modify/delete their own records."""
    if user is None:
        raise ProblemException(
            status_code=401,
            title="Authentication Required",
            detail="Authentication is required to modify this resource.",
            type_slug="authentication-required",
        )
    if user.role == "admin":
        return
    if user.role == "developer" and user.username == owner_username:
        return

    raise ProblemException(
        status_code=403,
        title="Forbidden",
        detail=(
            f"User '{user.username}' is not the owner ('{owner_username}') of this resource "
            "and lacks administrator privileges."
        ),
        type_slug="not-resource-owner",
    )
