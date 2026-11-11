import base64
import binascii
import hashlib
import secrets
from dataclasses import dataclass

from litestar.connection import ASGIConnection
from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult

from app.core.exceptions import ProblemException


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str  # "admin" | "developer" | "viewer"
    display_name: str


def _hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Stateless user directory with three distinct permission tiers
USERS_DB: dict[str, tuple[str, AuthenticatedUser]] = {
    "admin": (
        _hash_password("admin123"),
        AuthenticatedUser(username="admin", role="admin", display_name="Platform Administrator"),
    ),
    "dev_alice": (
        _hash_password("alice123"),
        AuthenticatedUser(username="dev_alice", role="developer", display_name="Alice (Site Reliability Engineer)"),
    ),
    "viewer_bob": (
        _hash_password("bob123"),
        AuthenticatedUser(username="viewer_bob", role="viewer", display_name="Bob (Security Auditor)"),
    ),
}


class StatelessBasicAuthMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        auth_header = connection.headers.get("authorization")

        # Anonymous access is allowed on public read endpoints; protected routes use guards
        if not auth_header:
            return AuthenticationResult(user=None, auth=None)

        scheme, _, credentials = auth_header.partition(" ")
        if scheme.lower() != "basic" or not credentials:
            raise ProblemException(
                status_code=401,
                title="Unauthorized",
                detail="Invalid authentication scheme. Use HTTP Basic Authentication.",
                type_slug="invalid-auth-scheme",
            )

        try:
            decoded = base64.b64decode(credentials.strip()).decode("utf-8")
            username, sep, password = decoded.partition(":")
            if not sep:
                raise ValueError("Missing colon separator")
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise ProblemException(
                status_code=401,
                title="Unauthorized",
                detail="Malformed HTTP Basic credentials.",
                type_slug="malformed-credentials",
            ) from exc

        record = USERS_DB.get(username)
        if record is None:
            raise ProblemException(
                status_code=401,
                title="Unauthorized",
                detail="Invalid username or password.",
                type_slug="invalid-credentials",
            )

        expected_hash, user_obj = record
        provided_hash = _hash_password(password)
        if not secrets.compare_digest(expected_hash, provided_hash):
            raise ProblemException(
                status_code=401,
                title="Unauthorized",
                detail="Invalid username or password.",
                type_slug="invalid-credentials",
            )

        return AuthenticationResult(user=user_obj, auth="basic")
