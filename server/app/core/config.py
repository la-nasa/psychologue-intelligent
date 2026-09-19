from __future__ import annotations

from functools import lru_cache
from pathlib import Path
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
    mq_enabled: bool = True

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
    smtp_from: str = "alerts@psychologue-intelligent.local"

    # Politiques cliniques versionnées (ADR-002/004). Copie v2 sous server/config/
    # pendant la migration ; cible = table `crisis_policies` (data-model-v2 §4).
    policy_dir: Path = Path("config/policies")
    crisis_policy_file: str = "crisis-policy-v1.json"
    crisis_rules_file: str = "crisis-rules-v1.json"
    response_templates_file: str = "response-templates-v1.json"

    # Chemin DEEP (ADR-007). Vide => chemin externe désactivé, dégradation locale.
    llm_external_provider: str = ""
    llm_external_api_key: str = ""
    llm_external_model: str = "claude-haiku-4-5"
    llm_external_base_url: str = ""
    llm_max_reply_tokens: int = 160

    # FAST local hybride (ADR-015). Vide => pas de serveur d'inférence HTTP.
    llm_base_url: str = ""
    llm_api_key: str = "local"
    fast_model: str = "Qwen/Qwen2.5-3B-Instruct"
    standard_model: str = "Qwen/Qwen2.5-3B-Instruct"
    deep_reasoning_model: str = "claude-haiku-4-5"
    llm_model_path: Path = Path("work/models/qwen2.5-0.5b-instruct-q4_k_m.gguf")
    llm_n_gpu_layers: int = -1
    llm_context_tokens: int = 4096
    llm_threads: int | None = None
    # Les tests n'ouvrent jamais un GGUF réel sauf activation explicite.
    llm_enable_in_tests: bool = False

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Phase 18 — hardening. Séparé de `env` : ce déploiement tourne délibérément en
    # `PI_ENV=development` (la politique de crise n'a pas d'`approved_by` clinique
    # réel, cf. crisis.py) tout en servant de vrais utilisateurs sur une URL
    # publique — `env` seul ne suffit donc pas à décider si /docs doit être exposé.
    expose_api_docs: bool = True

    # Phase 17 — MLOps (ADR-011). Vide => tracking désactivé, l'enregistrement de
    # version reste local (table `model_versions`) sans miroir MLflow.
    mlflow_tracking_uri: str = ""
    mlflow_tracking_username: str = ""
    mlflow_tracking_password: str = ""

    @property
    def is_production_like(self) -> bool:
        return self.env in ("staging", "shadow", "production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.env == "testing":
        # Limites de débit basses pour que les tests qui vérifient le mécanisme
        # n'aient pas à émettre des dizaines de requêtes réelles.
        settings = settings.model_copy(
            update={
                "rate_limit_message_per_min": 8,
                "rate_limit_register_per_hour": 100,
                "rate_limit_login_per_15min": 50,
                "rate_limit_phq9_per_hour": 6,
                "mq_enabled": False,  # pas de broker dans la suite de tests
            }
        )
    return settings
