from litestar.connection import ASGIConnection
from litestar.handlers.base import BaseRouteHandler

from app.core.enums import UserRole
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.security.auth import AuthenticatedUser


def require_authenticated(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    if connection.scope.get("user") is None:
        raise UnauthorizedError(
            "You must provide valid HTTP Basic credentials to access this resource."
        )


def require_writer(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None:
    require_authenticated(connection, route_handler)
    user: AuthenticatedUser = connection.user
    if user.role not in (UserRole.ADMIN, UserRole.DEVELOPER):
        raise ForbiddenError(
            f"User '{user.username}' with role '{user.role}' has read-only access."
        )


def require_admin(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None:
    require_authenticated(connection, route_handler)
    user: AuthenticatedUser = connection.user
    if user.role != UserRole.ADMIN:
        raise ForbiddenError(
            "Only users with the 'admin' role may perform this operation."
        )


def ensure_owner_or_admin(user: AuthenticatedUser | None, owner_username: str) -> None:
    """Enforces resource-level ownership: developers may only modify/delete their own records."""
    if user is None:
        raise UnauthorizedError("Authentication is required to modify this resource.")
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.DEVELOPER and user.username == owner_username:
        return

    raise ForbiddenError(
        f"User '{user.username}' is not the owner ('{owner_username}') of this resource "
        "and lacks administrator privileges."
    )
