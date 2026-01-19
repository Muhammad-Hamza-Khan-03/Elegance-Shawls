from fastapi import FastAPI
from contextlib import asynccontextmanager

from configuration.config import settings
from database.db import connect_to_mongo, close_mongo_connection
from routes.product_routes import router as product_router


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

    # Routers
    app.include_router(product_router)

    # Health Check
    @app.get("/health/", tags=["Health"])
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
