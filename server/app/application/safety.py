"""Pipeline de sûreté — porté de v1 `backend/app/pipeline.py`.

`message_reference` sert à la fois de pointeur d'entrée de la trace de risque et
de clé d'idempotence de l'alerte : rejouer le même message ne peut jamais créer
un doublon risk_assessment / crisis_event / alert (TM-09).

Le moteur de crise s'exécute AVANT toute génération et INDÉPENDAMMENT du LLM
(overview-v2 §15 invariant 1). Ce module ne connaît aucun `LLMProvider` — la
composition de la réponse (`domain/safety/responder.compose_reply`) est appelée
séparément par le moteur de conversation (Phase 4).
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.alerts import open_alert
from app.application.notifications import NotificationProvider, notify_alert
from app.core.config import Settings
from app.domain.safety.crisis import CrisisDecision, CrisisDetector, RiskModel
from app.domain.safety.policy import (
    CrisisPolicy,
    CrisisRules,
    ResponseTemplates,
    load_crisis_policy,
    load_crisis_rules,
    load_response_templates,
)
from app.infrastructure.models import CrisisEvent, RiskAssessment

LOGGER = logging.getLogger("pi.safety")
_ALERT_LEVELS = ("ORANGE", "RED")


@dataclass(frozen=True)
class SafetyConfig:
    policy: CrisisPolicy
    rules: CrisisRules
    templates: ResponseTemplates


def load_safety_config(settings: Settings) -> SafetyConfig:
    base: Path = settings.policy_dir
    policy = load_crisis_policy(base / settings.crisis_policy_file)
    rules = load_crisis_rules(base / settings.crisis_rules_file)
    templates = load_response_templates(base / settings.response_templates_file)
    if settings.is_production_like:
        # Défense en profondeur : le loader refuse déjà une politique non approuvée
        # hors development, on le re-vérifie explicitement ici au câblage.
        if not policy.approved_by or not templates.approved_by:
            raise RuntimeError("crisis policy / response templates are not clinically approved")
    return SafetyConfig(policy=policy, rules=rules, templates=templates)


@dataclass(frozen=True)
class MessageOutcome:
    decision: CrisisDecision
    crisis_event_id: uuid.UUID
    alert_id: uuid.UUID | None
    alert_created: bool
    notifications: tuple


async def evaluate_incoming_message(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    text: str,
    message_reference: str,
    config: SafetyConfig,
    risk_model: RiskModel,
    notification_provider: NotificationProvider,
    request_id: str,
    emotion: tuple[str, float, str] | None = None,
) -> MessageOutcome:
    detector = CrisisDetector(config.policy, config.rules)
    decision = detector.evaluate(text, risk_model)

    emotion_label = emotion[0] if emotion else None
    emotion_confidence = emotion[1] if emotion else None
    emotion_model_version = emotion[2] if emotion else None

    risk = RiskAssessment(
        id=uuid.uuid4(),
        organization_id=organization_id,
        patient_id=patient_id,
        input_reference=message_reference,
        score=decision.score,
        confidence=decision.confidence,
        model_version=decision.model_version,
        model_available=decision.model_available,
        emotion_label=emotion_label,
        emotion_confidence=emotion_confidence,
        emotion_model_version=emotion_model_version,
    )
    session.add(risk)
    await session.flush()

    crisis = CrisisEvent(
        id=uuid.uuid4(),
        organization_id=organization_id,
        risk_assessment_id=risk.id,
        patient_id=patient_id,
        level=decision.level,
        reasons=",".join(decision.reasons),
        rules_version=decision.rules_version,
        policy_version=decision.policy_version,
    )
    session.add(crisis)
    await session.flush()

    if decision.level not in _ALERT_LEVELS:
        return MessageOutcome(decision, crisis.id, None, False, ())

    sla_minutes = config.policy.response_sla_minutes.get(decision.level)
    sla_due_at = (
        dt.datetime.now(dt.UTC) + dt.timedelta(minutes=sla_minutes) if sla_minutes else None
    )
    alert, created = await open_alert(
        session,
        organization_id=organization_id,
        patient_id=patient_id,
        crisis_event_id=crisis.id,
        decision=decision,
        idempotency_key=message_reference,
        sla_due_at=sla_due_at,
    )
    outcomes: tuple = ()
    if created:
        outcomes = tuple(
            await notify_alert(
                session,
                alert=alert,
                channels=config.policy.notification_channels,
                provider=notification_provider,
                request_id=request_id,
            )
        )
    return MessageOutcome(decision, crisis.id, alert.id, created, outcomes)
