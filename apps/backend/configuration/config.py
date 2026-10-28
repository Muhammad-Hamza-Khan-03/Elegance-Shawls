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
    # Shared with the storefront server so server-rendered reads, which all come
    # from one address, are not limited as if they were a single client.
    internal_api_token: str = ""
    public_rate_limit_per_minute: int = 120
    admin_rate_limit_per_minute: int = 60

    # Phase 1 ingestion. Empty/unauthorized by default so nothing can fetch until an
    # operator deliberately configures one authorized source.
    ingestion_source_id: str = "primary"
    ingestion_source_name: str = ""
    ingestion_source_domain: str = ""
    ingestion_source_authorized: bool = False
    # Additional exact hosts (comma-separated) that belong to the same source, e.g. "www.example.com".
    # Redirects may move between the source domain and these hosts and nowhere else.
    ingestion_allowed_hosts: str = ""
    # Extra https hosts (comma-separated) product images may be served from, e.g. a CDN.
    ingestion_image_hosts: str = ""
    ingestion_connect_timeout_seconds: float = 5.0
    ingestion_read_timeout_seconds: float = 10.0
    ingestion_max_response_bytes: int = 2_000_000
    ingestion_max_redirects: int = 3
    ingestion_domain_min_interval_seconds: float = 2.0
    ingestion_job_max_attempts: int = 3
    ingestion_job_lease_seconds: int = 120
    ingestion_job_backoff_seconds: int = 30
    # One-shot refresh (python -m ingestion.worker --once). Sitemap is always on an approved host.
    ingestion_sitemap_path: str = "/sitemap.xml"
    ingestion_max_urls_per_source: int = 500
    ingestion_max_sitemaps: int = 50
    ingestion_run_max_seconds: int = 2700

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = settings()
