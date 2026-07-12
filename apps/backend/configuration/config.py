from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class settings(BaseSettings):
    MONGODB_URI: str
    MONGO_DB_NAME: str

    app_name: str = "Products API"
    environment: str = "development"
    allowed_origins: str = "http://localhost:3000"
    admin_api_key: str = ""
    public_rate_limit_per_minute: int = 120
    admin_rate_limit_per_minute: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = settings()
