from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

load_dotenv()

class settings(BaseSettings):
    MONGODB_URI:str
    MONGO_DB_NAME:str

    app_name:str = "Products API"
    environment:str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",case_sensitive=True)


settings = settings()