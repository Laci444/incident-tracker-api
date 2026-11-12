import base64
import binascii
import hashlib
import secrets
from dataclasses import dataclass

from litestar.connection import ASGIConnection
from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult

from app.core.enums import HttpHeader, UserRole
from app.core.exceptions import UnauthorizedError


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: UserRole
    display_name: str


def _hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


USERS_DB: dict[str, tuple[str, AuthenticatedUser]] = {
    "admin": (
        _hash_password("admin123"),
        AuthenticatedUser(
            username="admin",
            role=UserRole.ADMIN,
            display_name="Platform Administrator",
        ),
    ),
    "dev_alice": (
        _hash_password("alice123"),
        AuthenticatedUser(
            username="dev_alice",
            role=UserRole.DEVELOPER,
            display_name="Alice (Site Reliability Engineer)",
        ),
    ),
    "viewer_bob": (
        _hash_password("bob123"),
        AuthenticatedUser(
            username="viewer_bob",
            role=UserRole.VIEWER,
            display_name="Bob (Security Auditor)",
        ),
    ),
}


class StatelessBasicAuthMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(
        self, connection: ASGIConnection
    ) -> AuthenticationResult:
        auth_header = connection.headers.get(HttpHeader.AUTHORIZATION.lower())
        if not auth_header:
            return AuthenticationResult(user=None, auth=None)

        scheme, _, credentials = auth_header.partition(" ")
        if scheme.lower() != "basic" or not credentials:
            raise UnauthorizedError(
                "Invalid authentication scheme. Use HTTP Basic Authentication."
            )

        try:
            decoded = base64.b64decode(credentials.strip()).decode("utf-8")
            username, sep, password = decoded.partition(":")
            if not sep:
                raise ValueError("Missing colon separator")
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise UnauthorizedError("Malformed HTTP Basic credentials.") from exc

        record = USERS_DB.get(username)
        if record is None:
            raise UnauthorizedError("Invalid username or password.")

        expected_hash, user_obj = record
        if not secrets.compare_digest(expected_hash, _hash_password(password)):
            raise UnauthorizedError("Invalid username or password.")

        return AuthenticationResult(user=user_obj, auth="basic")
