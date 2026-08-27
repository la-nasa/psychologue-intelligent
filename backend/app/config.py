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
    # "templated" (default, zero dependency, ADR-003) or "local-llm" (ADR-005:
    # a self-hosted generative model for GREEN-level replies only -- ORANGE/RED
    # always come from fixed templates regardless of this setting, see responder.py).
    responder_mode: str = "templated"
    llm_model_path: Path = Path("work/models/qwen2.5-3b-instruct-q4_k_m.gguf")
    llm_context_tokens: int = 4096
    llm_max_reply_tokens: int = 220

    @classmethod
    def from_env(cls) -> Settings:
        path = Path(os.environ.get("PI_DATABASE_PATH", "work/psychologue-intelligent.db"))
        environment = os.environ.get("PI_ENV", "development")
        policy_path = Path(os.environ.get("PI_CRISIS_POLICY_PATH", "config/policies/crisis-policy-v1.json"))
        rules_path = Path(os.environ.get("PI_CRISIS_RULES_PATH", "config/policies/crisis-rules-v1.json"))
        templates_path = Path(os.environ.get("PI_RESPONSE_TEMPLATES_PATH", "config/policies/response-templates-v1.json"))
        emotion_path = Path(os.environ.get("PI_EMOTION_MODEL_PATH", "ml/artifacts/emotion-classifier-v1.json"))
        responder_mode = os.environ.get("PI_RESPONDER_MODE", "templated")
        llm_model_path = Path(os.environ.get("PI_LLM_MODEL_PATH", "work/models/qwen2.5-3b-instruct-q4_k_m.gguf"))
        llm_context_tokens = int(os.environ.get("PI_LLM_CONTEXT_TOKENS", "4096"))
        llm_max_reply_tokens = int(os.environ.get("PI_LLM_MAX_REPLY_TOKENS", "220"))
        return cls(
            database_path=path, environment=environment, crisis_policy_path=policy_path,
            crisis_rules_path=rules_path, response_templates_path=templates_path, emotion_model_path=emotion_path,
            responder_mode=responder_mode, llm_model_path=llm_model_path,
            llm_context_tokens=llm_context_tokens, llm_max_reply_tokens=llm_max_reply_tokens,
        )

