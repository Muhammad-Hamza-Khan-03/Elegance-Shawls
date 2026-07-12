from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from configuration.config import settings
from database.db import connect_to_mongo, close_mongo_connection, database_is_ready
from routes.product_routes import router as product_router
from security.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")
    await connect_to_mongo()
    yield
    # Shutdown
    print("Shutting down...")
    await close_mongo_connection()


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

    # Routers
    app.include_router(product_router)

    # Health Check
    @app.get("/health/", tags=["Health"])
    async def health_check():
        return {"status": "ok"}

    @app.get("/ready/", tags=["Health"])
    async def readiness_check(response: Response):
        if not await database_is_ready():
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "unavailable"}
        return {"status": "ready", "database": "connected"}

    return app


app = create_app()
