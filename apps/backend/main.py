from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from configuration.config import settings
from database.pg import close_postgres, connect_to_postgres, database_is_ready, postgres_configured
from database.redis_client import close_redis, redis_configured, redis_is_ready
from routes.product_routes import router as product_router, search_router
from routes.ingestion_routes import router as ingestion_router
from routes.event_routes import router as event_router
from routes.enquiry_routes import admin_router as enquiry_admin_router, router as enquiry_router
from routes.assistant_routes import router as assistant_router
from routes.job_routes import router as job_router
from routes.llm_routes import router as llm_router, admin_router as llm_admin_router
from routes.admin_routes import accounts_router, audit_router, auth_router
from observability.request_log import RequestLogMiddleware
from observability.tracing import configure_exporters
from security.admin_auth import legacy_key_enabled, legacy_key_expiry
from security.rate_limit import RateLimitMiddleware
from workers.queues import close_queue_pool, worker_is_alive


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")
    configure_exporters()  # no-op unless OTEL_ENABLED and an OTLP endpoint are set
    # PostgreSQL holds the catalogue, staged products and ingestion jobs, so it is required: a missing
    # DATABASE_URL is a configuration error and stops startup. A configured but unreachable database
    # does not (the pool reconnects); /ready/ reports 503 and data routes answer 503 until it is back.
    if not postgres_configured():
        raise RuntimeError("DATABASE_URL is required: the catalogue runs on PostgreSQL")
    await connect_to_postgres()
    if legacy_key_enabled():
        print(f"WARNING: the legacy shared ADMIN_API_KEY is accepted until {legacy_key_expiry().isoformat()}; migrate to individual admin accounts")
    yield
    # Shutdown
    print("Shutting down...")
    await close_queue_pool()
    await close_redis()
    await close_postgres()


async def _optional_status(configured: bool, probe, up: str = "connected", down: str = "unavailable") -> str:
    if not configured:
        return "disabled"
    return up if await probe() else down


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    # Added last so it is outermost and also logs rate-limited responses.
    app.add_middleware(RequestLogMiddleware)

    # Routers
    app.include_router(product_router)
    app.include_router(search_router)
    app.include_router(ingestion_router)
    app.include_router(job_router)
    app.include_router(llm_router)
    app.include_router(llm_admin_router)
    app.include_router(event_router)
    app.include_router(assistant_router)
    app.include_router(enquiry_router)
    app.include_router(enquiry_admin_router)
    app.include_router(auth_router)
    app.include_router(accounts_router)
    app.include_router(audit_router)

    # Health Check
    @app.get("/health/", tags=["Health"])
    async def health_check():
        return {"status": "ok"}

    @app.get("/ready/", tags=["Health"])
    async def readiness_check(response: Response):
        if not await database_is_ready():
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "unavailable"}
        # PostgreSQL is the database: it alone gates readiness. Redis and the AI worker are optional and only reported.
        return {
            "status": "ready",
            "database": "connected",
            "postgres": "connected",
            "redis": await _optional_status(redis_configured(), redis_is_ready),
            "worker": await _optional_status(redis_configured(), worker_is_alive, "alive", "not_seen"),
        }

    return app


app = create_app()
