from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "staging", "shadow", "production"]


class Settings(BaseSettings):
    """Configuration issue de l'environnement (préfixe ``PI_``).

    Aucun défaut n'est un secret réel. En production, ``PI_JWT_SIGNING_KEY`` et
    les URL de service sont injectés par le gestionnaire de secrets (§95).
    """

    model_config = SettingsConfigDict(env_prefix="PI_", env_file=".env", extra="ignore")

    env: Environment = "development"

    database_url: str = "postgresql+asyncpg://pi:pi_dev_only@localhost:5432/psychologue_intelligent"
    database_url_sync: str = "postgresql+psycopg://pi:pi_dev_only@localhost:5432/psychologue_intelligent"
    db_pool_size: int = 10
    db_max_overflow: int = 5

    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://pi:pi_dev_only@localhost:5672/"

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "pi-api"
    otel_enabled: bool = True

    jwt_signing_key: str = "dev-only-not-a-real-secret-change-me"
    session_ttl_seconds: int = 60 * 60 * 8
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 64 * 1024
    argon2_parallelism: int = 4

    # Rate limiting distribué (Redis) — threat-model-v2 TH-10, TV-13
    rate_limit_login_per_15min: int = 5
    rate_limit_register_per_hour: int = 10
    rate_limit_message_per_min: int = 30
    rate_limit_phq9_per_hour: int = 20

    smtp_host: str = "localhost"
    smtp_port: int = 1025

    llm_external_provider: str = ""
    llm_external_api_key: str = ""

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def is_production_like(self) -> bool:
        return self.env in ("staging", "shadow", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
