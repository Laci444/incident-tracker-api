from enum import StrEnum


class ApiVersion(StrEnum):
    V1 = "v1"
    # V2 = "v2"

    # Active default version served by this instance
    CURRENT = V1


class ResourceName(StrEnum):
    API = "api"
    VERSION_INDEX = "version_index"
    PROFILE = "profile"
    SERVICE = "service"
    RELEASE = "release"
    INCIDENT = "incident"


class CollectionName(StrEnum):
    SERVICES = "services"
    RELEASES = "releases"
    INCIDENTS = "incidents"


class PathParam(StrEnum):
    """Centralized path parameter names derived from ResourceName."""

    SERVICE_ID = f"{ResourceName.SERVICE}_id"
    RELEASE_ID = f"{ResourceName.RELEASE}_id"
    INCIDENT_ID = f"{ResourceName.INCIDENT}_id"


class ApiPath(StrEnum):
    """URI patterns dynamically composed from ResourceName, CollectionName, and ApiVersion."""

    ROOT = f"/{ResourceName.API}"
    V1_PREFIX = f"{ROOT}/{ApiVersion.V1}"
    # V2_PREFIX = f"{ROOT}/{ApiVersion.V2}"
    CURRENT_PREFIX = f"{ROOT}/{ApiVersion.CURRENT}"

    ME = "/me"

    SERVICES = f"/{CollectionName.SERVICES}"
    SERVICE_ITEM = f"{SERVICES}/{{{PathParam.SERVICE_ID}:int}}"

    SERVICE_RELEASES = f"{SERVICE_ITEM}/{CollectionName.RELEASES}"
    RELEASE_ITEM = f"/{CollectionName.RELEASES}/{{{PathParam.RELEASE_ID}:int}}"

    INCIDENTS = f"/{CollectionName.INCIDENTS}"
    INCIDENT_ITEM = f"{INCIDENTS}/{{{PathParam.INCIDENT_ID}:int}}"

    SCHEMA_ROOT = "/schema"
    OPENAPI_JSON = f"{SCHEMA_ROOT}/openapi.json"
    OPENAPI_YAML = f"{SCHEMA_ROOT}/openapi.yaml"
    SWAGGER_UI = f"{SCHEMA_ROOT}/swagger"


class RouteName(StrEnum):
    """Version-agnostic logical route identifiers built from domain resource names."""

    API_DISCOVERY = f"{ResourceName.API}_discovery"
    API_DISCOVERY_OPTIONS = f"{ResourceName.API}_discovery_options"

    VERSION_ROOT = f"{ResourceName.VERSION_INDEX}_root"
    VERSION_ROOT_OPTIONS = f"{ResourceName.VERSION_INDEX}_root_options"

    ME = f"{ResourceName.PROFILE}_me"
    ME_OPTIONS = f"{ResourceName.PROFILE}_me_options"

    SERVICES_LIST = f"{CollectionName.SERVICES}_list"
    SERVICES_CREATE = f"{CollectionName.SERVICES}_create"
    SERVICES_OPTIONS = f"{CollectionName.SERVICES}_options"
    SERVICE_DETAIL = f"{ResourceName.SERVICE}_detail"
    SERVICE_REPLACE = f"{ResourceName.SERVICE}_replace"
    SERVICE_PATCH = f"{ResourceName.SERVICE}_patch"
    SERVICE_DELETE = f"{ResourceName.SERVICE}_delete"
    SERVICE_ITEM_OPTIONS = f"{ResourceName.SERVICE}_item_options"

    SERVICE_RELEASES_LIST = f"{ResourceName.SERVICE}_{CollectionName.RELEASES}_list"
    SERVICE_RELEASES_CREATE = f"{ResourceName.SERVICE}_{CollectionName.RELEASES}_create"
    SERVICE_RELEASES_OPTIONS = (
        f"{ResourceName.SERVICE}_{CollectionName.RELEASES}_options"
    )
    RELEASE_DETAIL = f"{ResourceName.RELEASE}_detail"
    RELEASE_PATCH = f"{ResourceName.RELEASE}_patch"
    RELEASE_DELETE = f"{ResourceName.RELEASE}_delete"
    RELEASE_ITEM_OPTIONS = f"{ResourceName.RELEASE}_item_options"

    INCIDENTS_LIST = f"{CollectionName.INCIDENTS}_list"
    INCIDENTS_CREATE = f"{CollectionName.INCIDENTS}_create"
    INCIDENTS_OPTIONS = f"{CollectionName.INCIDENTS}_options"
    INCIDENT_DETAIL = f"{ResourceName.INCIDENT}_detail"
    INCIDENT_REPLACE = f"{ResourceName.INCIDENT}_replace"
    INCIDENT_PATCH = f"{ResourceName.INCIDENT}_patch"
    INCIDENT_DELETE = f"{ResourceName.INCIDENT}_delete"
    INCIDENT_ITEM_OPTIONS = f"{ResourceName.INCIDENT}_item_options"

    def versioned(self, version: ApiVersion = ApiVersion.CURRENT) -> str:
        """Returns a version-namespaced route name for multi-version routers."""
        return f"{version}:{self.value}"


class MediaType(StrEnum):
    HAL_JSON = "application/hal+json"
    JSON = "application/json"
    XML = "application/xml"
    TEXT_XML = "text/xml"
    MERGE_PATCH_JSON = "application/merge-patch+json"
    PROBLEM_JSON = "application/problem+json"
    PROBLEM_XML = "application/problem+xml"
    WILDCARD = "*/*"
    APP_WILDCARD = "application/*"


class HttpMethod(StrEnum):
    GET = "GET"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class HttpHeader(StrEnum):
    ACCEPT = "Accept"
    ACCEPT_PATCH = "Accept-Patch"
    ALLOW = "Allow"
    AUTHORIZATION = "Authorization"
    CACHE_CONTROL = "Cache-Control"
    CONTENT_LENGTH = "Content-Length"
    CONTENT_SECURITY_POLICY = "Content-Security-Policy"
    CONTENT_TYPE = "Content-Type"
    ETAG = "ETag"
    IF_MATCH = "If-Match"
    IF_MODIFIED_SINCE = "If-Modified-Since"
    IF_NONE_MATCH = "If-None-Match"
    LAST_MODIFIED = "Last-Modified"
    LINK = "Link"
    LOCATION = "Location"
    VARY = "Vary"
    WWW_AUTHENTICATE = "WWW-Authenticate"


class LinkRel(StrEnum):
    """IANA-registered link relation types."""

    SELF = "self"
    COLLECTION = "collection"
    ITEM = "item"
    UP = "up"
    RELATED = "related"
    AUTHOR = "author"
    FIRST = "first"
    NEXT = "next"
    PREV = "prev"
    CREATE_FORM = "create-form"
    EDIT = "edit"
    DELETE = "delete"
    DESCRIBEDBY = "describedby"
    HELP = "help"
    LATEST_VERSION = "latest-version"
    PREDECESSOR_VERSION = "predecessor-version"
    SERVICE_DESC = "service-desc"


class UserRole(StrEnum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class ServiceTier(StrEnum):
    TIER_1 = "tier-1"
    TIER_2 = "tier-2"
    TIER_3 = "tier-3"


class ReleaseEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


class ProblemTypeUri(StrEnum):
    BAD_REQUEST = "urn:problem-type:bad-request"
    UNAUTHORIZED = "urn:problem-type:unauthorized"
    FORBIDDEN = "urn:problem-type:forbidden"
    NOT_FOUND = "urn:problem-type:resource-not-found"
    METHOD_NOT_ALLOWED = "urn:problem-type:method-not-allowed"
    NOT_ACCEPTABLE = "urn:problem-type:not-acceptable"
    CONFLICT = "urn:problem-type:resource-conflict"
    PRECONDITION_FAILED = "urn:problem-type:precondition-failed"
    UNSUPPORTED_MEDIA_TYPE = "urn:problem-type:unsupported-media-type"
    VALIDATION_ERROR = "urn:problem-type:validation-error"
    INTERNAL_ERROR = (
        "https://iana.org/assignments/http-problem-types#internal-server-error"
    )
