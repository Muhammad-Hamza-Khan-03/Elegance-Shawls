from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # Application
    APP_NAME: str = "Elegance-Shawls API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # JWT
    JWT_SECRET_KEY: str  
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Supabase database
    HOST: str
    SUPABASE_PORT: int
    SUPABASE_DB: str
    SUPABASE_USER: str
    SUPABASE_PASSWORD: str

    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None

    
    # SMTP Email
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool | None = None
    FROM_EMAIL: str | None = None

    # CORS
    FRONTEND_URL: str 
    MY_DOMAIN: str | None = None
    ALLOWED_ORIGINS: str | None = None

    # Business Info
    SUPPORT_WHATSAPP: str | None = None
    SUPPORT_EMAIL: str | None = None

    REDIS_DB_NAME:str | None = None
    REDIS_HOST:str | None = None
    REDIS_PASSWORD:str | None = None
    REDIS_PORT:str | None = None
    REDIS_USERNAME:str | None = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
