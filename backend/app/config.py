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

    @classmethod
    def from_env(cls) -> Settings:
        path = Path(os.environ.get("PI_DATABASE_PATH", "work/psychologue-intelligent.db"))
        environment = os.environ.get("PI_ENV", "development")
        policy_path = Path(os.environ.get("PI_CRISIS_POLICY_PATH", "config/policies/crisis-policy-v1.json"))
        rules_path = Path(os.environ.get("PI_CRISIS_RULES_PATH", "config/policies/crisis-rules-v1.json"))
        templates_path = Path(os.environ.get("PI_RESPONSE_TEMPLATES_PATH", "config/policies/response-templates-v1.json"))
        emotion_path = Path(os.environ.get("PI_EMOTION_MODEL_PATH", "ml/artifacts/emotion-classifier-v1.json"))
        return cls(
            database_path=path, environment=environment, crisis_policy_path=policy_path,
            crisis_rules_path=rules_path, response_templates_path=templates_path, emotion_model_path=emotion_path,
        )

