from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

# Create SQLAlchemy engine
# The pool settings ensure efficient connection management
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using them
    pool_size=10,
    max_overflow=20
)

# Session factory for creating database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models
Base = declarative_base()

def get_db():
    """
    Dependency that provides a database session to route handlers.
    Automatically closes the session after the request is complete.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()