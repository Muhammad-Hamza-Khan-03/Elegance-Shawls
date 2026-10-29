from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class settings(BaseSettings):
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

    # PostgreSQL is the sole database and is required by the API and the ingestion worker.
    database_url: str = ""
    pg_pool_size: int = 5
    pg_max_overflow: int = 5
    pg_pool_timeout_seconds: float = 5.0
    pg_connect_timeout_seconds: float = 3.0

    # Redis/arq for new AI workloads and shared rate limits. Empty = disabled.
    redis_url: str = ""
    redis_connect_timeout_seconds: float = 1.0
    worker_queue: str = "elegance:ai:default"
    worker_max_jobs: int = 4
    worker_job_timeout_seconds: int = 120
    worker_max_tries: int = 3

    # Anonymous interaction events. The signing key is required to accept events.
    session_signing_key: str = ""
    events_max_batch: int = 20
    events_max_body_bytes: int = 32_768
    events_rate_limit_per_minute: int = 30
    events_retention_months: int = 18

    # LLM gateway (logical names -> provider chains, env-only; keys live in provider env vars).
    llm_chain_default: str = ""
    llm_production_chain: str = ""
    llm_free_tier_providers: str = "groq,gemini,openrouter"
    llm_daily_budget_usd: float = 1.0
    llm_environment_budget_usd: float = 10.0
    llm_budget_warn_ratio: float = 0.8
    # Applied only when a provider reports no cost; 0 = unpriced (free tiers, local models).
    llm_price_per_million_input_usd: float = 0.0
    llm_price_per_million_output_usd: float = 0.0
    llm_max_attempts: int = 3
    llm_timeout_seconds: float = 20.0
    # Staged-product enrichment suggestions (P1-S3). Empty model = disabled. Attempts (2) are fixed by the contract.
    enrichment_model: str = ""
    enrichment_backoff_seconds: float = 1.0
    enrichment_backoff_cap_seconds: float = 8.0
    # Catalogue embeddings (P1-S4b). Off and provider-less by default: nothing embeds until an operator opts in.
    embedding_enabled: bool = False
    embedding_provider: str = ""
    embedding_dimensions: int = 768  # must equal the vector column width (models.relational_model.EMBEDDING_DIMENSIONS)
    embedding_index_version: str = "hnsw-cosine-m16-efc64-v1"
    embedding_max_jobs: int = 2
    embedding_job_timeout_seconds: int = 60
    embedding_max_attempts: int = 3
    embedding_lease_seconds: int = 90
    embedding_backoff_seconds: float = 30.0
    embedding_backfill_max_limit: int = 500
    # Advisory provider model discovery; cache is fresh for 6h and serveable stale for 48h.
    llm_discovery_fresh_ttl_seconds: int = 6 * 3600
    llm_discovery_stale_ceiling_seconds: int = 48 * 3600
    llm_discovery_timeout_seconds: float = 5.0
    llm_discovery_max_attempts: int = 3
    llm_discovery_retry_after_cap_seconds: float = 2.0

    # Observability. Exporters stay off unless explicitly enabled.
    otel_enabled: bool = False
    # Optional Langfuse LLM tracing. All three must be set (env only) or nothing is sent.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # an older .env may still hold keys for the retired previous database
    )


settings = settings()
