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


@lru_cache
def get_settings() -> Settings:
    return Settings()
