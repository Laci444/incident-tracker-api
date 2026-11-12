from litestar import Litestar, Router
from litestar.di import Provide
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import cors_config, openapi_config
from app.controllers.incidents import IncidentController
from app.controllers.releases import ReleaseController
from app.controllers.root import DiscoveryController, VersionRootController
from app.controllers.services import ServiceController
from app.core.caching import early_conditional_request_hook, warm_up_cache_registry
from app.core.enums import ApiPath
from app.core.exceptions import problem_exception_handler
from app.core.middleware import ProtocolNegotiationMiddleware, SecurityHeadersMiddleware
from app.core.renderers import HalNegotiatedResponse
from app.db.base import provide_db_session
from app.db.seed import init_db_and_seed
from app.security.auth import StatelessBasicAuthMiddleware
from app.services.incidents import IncidentService
from app.services.releases import ReleaseService
from app.services.service_catalog import ServiceCatalogService


async def provide_service_catalog(db_session: AsyncSession) -> ServiceCatalogService:
    return ServiceCatalogService(db_session)


async def provide_release_service(db_session: AsyncSession) -> ReleaseService:
    return ReleaseService(db_session)


async def provide_incident_service(db_session: AsyncSession) -> IncidentService:
    return IncidentService(db_session)


async def startup_lifecycle() -> None:
    await init_db_and_seed()
    await warm_up_cache_registry()


v1_router = Router(
    path=ApiPath.V1_PREFIX.value,
    route_handlers=[
        VersionRootController,
        ServiceController,
        ReleaseController,
        IncidentController,
    ],
)

app = Litestar(
    route_handlers=[
        DiscoveryController,
        v1_router,
    ],
    dependencies={
        "db_session": Provide(provide_db_session),
        "service_catalog": Provide(provide_service_catalog),
        "release_service": Provide(provide_release_service),
        "incident_service": Provide(provide_incident_service),
    },
    response_class=HalNegotiatedResponse,
    before_request=early_conditional_request_hook,
    middleware=[
        SecurityHeadersMiddleware,
        ProtocolNegotiationMiddleware,
        StatelessBasicAuthMiddleware,
    ],
    exception_handlers={Exception: problem_exception_handler},
    cors_config=cors_config,
    openapi_config=openapi_config,
    on_startup=[startup_lifecycle],
)
