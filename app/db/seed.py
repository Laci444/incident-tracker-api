from sqlalchemy import select

from app.db.base import Base, async_session_factory, engine
from app.db.models import IncidentModel, ReleaseModel, ServiceModel


async def init_db_and_seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        existing_service = await session.scalar(select(ServiceModel.id).limit(1))
        # Skip seeding if database already contains persisted records
        if existing_service is not None:
            return

        auth_service = ServiceModel(
            name="Identity & Auth Gateway",
            slug="identity-auth-gateway",
            description="Central OAuth2/OIDC token issuer and edge authentication service.",
            tier="tier-1",
            owner_team="Platform Security",
            is_active=True,
        )
        billing_service = ServiceModel(
            name="Payment Processing Engine",
            slug="payment-processing-engine",
            description="Handles invoice generation, ledger transactions, and webhook retries.",
            tier="tier-1",
            owner_team="Core FinTech",
            is_active=True,
        )
        notification_service = ServiceModel(
            name="Notification Dispatcher",
            slug="notification-dispatcher",
            description="Asynchronous email and webhook delivery worker.",
            tier="tier-2",
            owner_team="Customer Engagement",
            is_active=True,
        )

        session.add_all([auth_service, billing_service, notification_service])
        await session.flush()

        rel_auth_v1 = ReleaseModel(
            service_id=auth_service.id,
            version="v2.4.0",
            commit_sha="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            environment="production",
            release_notes="Added PKCE enforcement and rotated signing keys.",
            deployed_by="admin",
        )
        rel_auth_v2 = ReleaseModel(
            service_id=auth_service.id,
            version="v2.4.1",
            commit_sha="f0e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d",
            environment="production",
            release_notes="Hotfix for connection pool exhaustion under high load.",
            deployed_by="dev_alice",
        )
        rel_billing_v1 = ReleaseModel(
            service_id=billing_service.id,
            version="v1.12.0",
            commit_sha="1234567890abcdef1234567890abcdef12345678",
            environment="production",
            release_notes="Introduced idempotency keys for batch settlement API.",
            deployed_by="dev_alice",
        )

        session.add_all([rel_auth_v1, rel_auth_v2, rel_billing_v1])
        await session.flush()

        inc_1 = IncidentModel(
            service_id=auth_service.id,
            release_id=rel_auth_v1.id,
            title="Elevated 503 responses on token endpoint",
            summary="Database connection pool saturated after deploying v2.4.0.",
            severity="critical",
            status="mitigated",
            resolution_notes="Rolled forward to v2.4.1 with increased pool limits.",
            reported_by="dev_alice",
        )
        inc_2 = IncidentModel(
            service_id=billing_service.id,
            release_id=rel_billing_v1.id,
            title="Delayed webhook delivery for EU merchants",
            summary="Retry queue backlog exceeded threshold for 12 minutes.",
            severity="medium",
            status="open",
            resolution_notes=None,
            reported_by="admin",
        )
        inc_3 = IncidentModel(
            service_id=notification_service.id,
            release_id=None,
            title="SMTP relay intermittent TLS handshake timeout",
            summary="Upstream provider experienced brief packet loss in eu-central-1.",
            severity="low",
            status="resolved",
            resolution_notes="Provider rerouted traffic; verified zero dropped messages.",
            reported_by="dev_alice",
        )

        session.add_all([inc_1, inc_2, inc_3])
        await session.commit()
