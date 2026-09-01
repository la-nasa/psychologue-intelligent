"""Moteur de crise — porté de v1 `backend/app/crisis.py` (ADR-004, invariant 1).

Indépendant du LLM. Évalue chaque message via des règles versionnées et, quand
il est disponible, un modèle de risque. Une défaillance du modèle n'abaisse
jamais la prudence : elle n'ajoute qu'un signal au moteur de règles, ne le
remplace jamais. Combinaison par maximum de score / minimum de confiance.
Pur, sans I/O.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.domain.safety.policy import CrisisPolicy, CrisisRules

LOGGER = logging.getLogger("pi.safety.crisis")

MAX_MESSAGE_CHARS = 8_000


class RiskModel(Protocol):
    version: str

    def predict(self, text: str) -> tuple[float, float]: ...


@dataclass(frozen=True)
class CrisisDecision:
    level: str
    score: float
    confidence: float
    model_version: str
    model_available: bool
    rules_version: str
    policy_version: str
    reasons: tuple[str, ...]


def normalize(text: str) -> str:
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ValueError("invalid message")
    folded = text.casefold()
    stripped = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in stripped if not unicodedata.combining(ch))


def _rule_signal(normalized_text: str, rules: CrisisRules) -> tuple[float, float, tuple[str, ...]]:
    if any(term in normalized_text for term in rules.high_risk_terms):
        return 0.95, 0.90, ("rule_high_risk_term",)
    if any(term in normalized_text for term in rules.concern_terms):
        return 0.55, 0.80, ("rule_concern_term",)
    return 0.0, 0.80, ()


class CrisisDetector:
    def __init__(self, policy: CrisisPolicy, rules: CrisisRules) -> None:
        self.policy, self.rules = policy, rules

    def evaluate(self, text: str, model: RiskModel) -> CrisisDecision:
        normalized = normalize(text)
        rule_score, rule_confidence, rule_reasons = _rule_signal(normalized, self.rules)

        model_available = True
        model_score = model_confidence = 0.0
        model_version = "unavailable"
        try:
            model_score, model_confidence = model.predict(text)
            if not (0 <= model_score <= 1 and 0 <= model_confidence <= 1):
                raise ValueError("model produced an out-of-range score or confidence")
            model_version = model.version
        except Exception:
            LOGGER.exception("risk model unavailable; falling back to rule engine only")
            model_available = False

        if model_available:
            score = max(rule_score, model_score)
            confidence = min(rule_confidence, model_confidence)
            reasons = rule_reasons + (("model_signal",) if model_score >= self.policy.orange_score else ())
        else:
            score = rule_score
            confidence = min(rule_confidence, 0.5)
            reasons = (*rule_reasons, "model_unavailable")

        if score >= self.policy.red_score:
            level = "RED"
        elif score >= self.policy.orange_score or confidence < self.policy.orange_confidence_floor:
            level = "ORANGE"
            if not reasons:
                reasons = ("uncertainty",)
        else:
            level = "GREEN"
            reasons = reasons or ("no_elevated_signal",)

        return CrisisDecision(
            level=level,
            score=score,
            confidence=confidence,
            model_version=model_version,
            model_available=model_available,
            rules_version=self.rules.version,
            policy_version=self.policy.version,
            reasons=reasons,
        )
