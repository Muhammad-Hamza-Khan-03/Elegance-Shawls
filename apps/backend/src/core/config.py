from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    This centralizes all configuration and makes the app easy to deploy.
    """
    
    # Application
    APP_NAME: str = os.getenv("APP_NAME","")
    APP_VERSION: str = os.getenv("APP_VERSION","1.0.0")
    DEBUG: bool = os.getenv("DEBUG","False").lower() in ("true", "1", "t")
    
    # Security
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY","abc") # Used for JWT token generation
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Supabase Database
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    DATABASE_URL: str = os.getenv("SUPABASE_URL","") 
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME","")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY","")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET","")
    
    # Resend Email
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY","")
    FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL","")
    
    # CORS
    MY_DOMAIN: str = os.getenv("FRONTEND_PRODUCTION_URL","")
    ALLOWED_ORIGINS: str = "http://localhost:3000" + f",{MY_DOMAIN}"
    
    # Business
    SUPPORT_WHATSAPP: str = os.getenv("SUPPORT_WHATSAPP","")
    SUPPORT_EMAIL: str = os.getenv("SUPPORT_EMAIL","")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create a global settings instance
settings = Settings()