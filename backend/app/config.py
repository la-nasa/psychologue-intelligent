from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    session_ttl_seconds: int = 60 * 60 * 8
    password_iterations: int = 600_000
    environment: str = "development"
    crisis_policy_path: Path = Path("config/policies/crisis-policy-v1.json")
    crisis_rules_path: Path = Path("config/policies/crisis-rules-v1.json")
    response_templates_path: Path = Path("config/policies/response-templates-v1.json")
    emotion_model_path: Path = Path("ml/artifacts/emotion-classifier-v1.json")
    responder_mode: str = "templated"
    llm_model_path: Path = Path("work/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")
    llm_context_tokens: int = 4096
    llm_max_reply_tokens: int = 120
    llm_base_url: str = "http://127.0.0.1:8001/v1"
    llm_api_key: str = "local"
    llm_timeout_seconds: float = 8.0
    llm_backend_order: tuple[str, ...] = ("openai-compatible", "in-process", "template")
    fast_model: str = "fast-local"
    deep_model: str = "deep-local"
    fast_model_path: Path | None = None
    deep_model_path: Path | None = None
    fast_max_tokens: int = 96
    deep_max_tokens: int = 180
    realtime_enabled: bool = False
    mlflow_tracking_uri: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        def path(name: str, default: str) -> Path:
            return Path(os.environ.get(name, default))

        order = tuple(x.strip() for x in os.environ.get("PI_LLM_BACKEND_ORDER", "openai-compatible,in-process,template").split(",") if x.strip())
        fast_path = os.environ.get("PI_FAST_MODEL_PATH")
        deep_path = os.environ.get("PI_DEEP_MODEL_PATH")
        return cls(
            database_path=path("PI_DATABASE_PATH", "work/psychologue-intelligent.db"),
            environment=os.environ.get("PI_ENV", "development"),
            crisis_policy_path=path("PI_CRISIS_POLICY_PATH", "config/policies/crisis-policy-v1.json"),
            crisis_rules_path=path("PI_CRISIS_RULES_PATH", "config/policies/crisis-rules-v1.json"),
            response_templates_path=path("PI_RESPONSE_TEMPLATES_PATH", "config/policies/response-templates-v1.json"),
            emotion_model_path=path("PI_EMOTION_MODEL_PATH", "ml/artifacts/emotion-classifier-v1.json"),
            responder_mode=os.environ.get("PI_RESPONDER_MODE", "templated"),
            llm_model_path=path("PI_LLM_MODEL_PATH", "work/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
            llm_context_tokens=int(os.environ.get("PI_LLM_CONTEXT_TOKENS", "4096")),
            llm_max_reply_tokens=int(os.environ.get("PI_LLM_MAX_REPLY_TOKENS", "120")),
            llm_base_url=os.environ.get("PI_LLM_BASE_URL", "http://127.0.0.1:8001/v1").rstrip("/"),
            llm_api_key=os.environ.get("PI_LLM_API_KEY", "local"),
            llm_timeout_seconds=float(os.environ.get("PI_LLM_TIMEOUT_SECONDS", "8")),
            llm_backend_order=order,
            fast_model=os.environ.get("PI_FAST_MODEL", "fast-local"),
            deep_model=os.environ.get("PI_DEEP_MODEL", "deep-local"),
            fast_model_path=Path(fast_path) if fast_path else None,
            deep_model_path=Path(deep_path) if deep_path else None,
            fast_max_tokens=int(os.environ.get("PI_FAST_MAX_TOKENS", "96")),
            deep_max_tokens=int(os.environ.get("PI_DEEP_MAX_TOKENS", "180")),
            realtime_enabled=os.environ.get("PI_REALTIME_ENABLED", "false").lower() == "true",
            mlflow_tracking_uri=os.environ.get("MLFLOW_TRACKING_URI") or None,
        )
