from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "sentinelkyc"
    postgres_user: str = "sentinelkyc"
    postgres_password: str = "change-me"
    database_url: str = ""
    database_url_sync: str = ""

    redis_url: str = "redis://localhost:6379/0"

    # Vite dev server origins for the console/portal frontend (Phase 8).
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    ofac_sdn_url: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML"
    )
    ofac_sdn_advanced_url: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/"
        "SDN_ADVANCED.XML"
    )
    ofac_consolidated_url: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/"
        "CONSOLIDATED.XML"
    )
    ofac_xsd_url: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML.xsd"
    )
    ofac_min_record_count: int = Field(default=10000)
    ofac_poll_interval_hours: int = 6

    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_batch_size: int = 256

    dataset_raw_dir: str = "dataset/raw"
    dataset_processed_dir: str = "dataset/processed"

    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_access_token_minutes: int = 15
    jwt_issuer: str = "sentinelkyc"

    refresh_token_days: int = 7

    encryption_master_key: str = ""
    encryption_key_version: int = 1
    blind_index_key: str = ""

    totp_issuer: str = "SentinelKYC"

    login_lockout_threshold: int = 5
    login_lockout_base_seconds: int = 30

    rate_limit_login: str = "5/minute"
    rate_limit_api: str = "300/minute"

    # Restricted role the running application (not migrations, not the
    # Dagster pipelines) connects as: no superuser, RLS not bypassed,
    # INSERT/SELECT only on audit_log. See migration 0004 and Phase 4.4.
    app_db_user: str = "sentinelkyc_app"
    app_db_password: str = ""
    app_database_url: str = ""
    app_database_url_sync: str = ""

    # --- LLM (Phase 6) ---
    # The deterministic pipeline makes every routing decision; the LLM only
    # drafts case summaries and decision rationale. Quota numbers are
    # defaults for the free tiers of each console as of Phase 6 and should
    # be tuned to whatever the account's console actually shows.
    llm_enabled: bool = True
    llm_primary: str = "groq"  # groq | gemini
    llm_timeout_seconds: int = 8
    llm_circuit_breaker_failures: int = 5
    llm_circuit_breaker_cooldown_seconds: int = 60

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_rpm: int = 30
    groq_rpd: int = 14400
    groq_tpm: int = 6000

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_rpm: int = 15
    gemini_rpd: int = 1500
    gemini_tpm: int = 1_000_000

    def sync_database_url(self) -> str:
        if self.database_url_sync:
            return self.database_url_sync
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def app_sync_database_url(self) -> str:
        if self.app_database_url_sync:
            return self.app_database_url_sync
        return (
            f"postgresql+psycopg2://{self.app_db_user}:{self.app_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
