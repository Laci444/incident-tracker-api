from litestar import Litestar
from litestar.di import Provide

from app.config import cors_config, openapi_config
from app.controllers.incidents import IncidentController
from app.controllers.releases import ReleaseController
from app.controllers.root import RootController
from app.controllers.services import ServiceController
from app.core.exceptions import problem_exception_handler
from app.core.middleware import ProtocolComplianceMiddleware
from app.db.base import provide_db_session
from app.db.seed import init_db_and_seed
from app.security.auth import StatelessBasicAuthMiddleware

app = Litestar(
    route_handlers=[
        RootController,
        ServiceController,
        ReleaseController,
        IncidentController,
    ],
    dependencies={"db_session": Provide(provide_db_session)},
    middleware=[
        ProtocolComplianceMiddleware,
        StatelessBasicAuthMiddleware,
    ],
    exception_handlers={Exception: problem_exception_handler},
    cors_config=cors_config,
    openapi_config=openapi_config,
    on_startup=[init_db_and_seed],
)
