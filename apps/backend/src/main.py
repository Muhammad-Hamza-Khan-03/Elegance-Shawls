from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.database import engine, Base
from .api import auth, products, variants, orders, admin, cart

# Create database tables
Base.metadata.create_all(bind=engine)
print("Database Initialized")

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API for the Fashion Fusion e-commerce platform",
    debug=settings.DEBUG
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router,prefix=settings.API_PREFIX)
app.include_router(products.router,prefix=settings.API_PREFIX)
app.include_router(variants.router,prefix=settings.API_PREFIX)
app.include_router(orders.router,prefix=settings.API_PREFIX)
app.include_router(admin.router,prefix=settings.API_PREFIX)
app.include_router(cart.router,prefix=settings.API_PREFIX)

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
