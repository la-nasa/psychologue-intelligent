from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from .alerts import open_alert
from .auth import utc_now
from .crisis import CrisisDecision, CrisisDetector, RiskModel
from .emotion import EmotionModel, top_prediction
from .notifications import NotificationProvider, notify_alert
from .policy import CrisisPolicy, CrisisRules

ALERT_LEVELS_REQUIRING_ALERT = ("ORANGE", "RED")
LOGGER = logging.getLogger("psychologue_intelligent.pipeline")


@dataclass(frozen=True)
class MessageOutcome:
    decision: CrisisDecision
    crisis_event_id: str
    alert: dict | None
    alert_created: bool
    notifications: tuple


def handle_incoming_message(
    conn,
    patient_id: str,
    text: str,
    message_reference: str,
    model: RiskModel,
    policy: CrisisPolicy,
    rules: CrisisRules,
    provider: NotificationProvider,
    request_id: str,
    emotion_model: EmotionModel | None = None,
) -> MessageOutcome:
    """message_reference is used both as the risk trail's input pointer and as the
    alert idempotency key: when the caller passes a real messages.id (see
    conversation.py), retrying the same message can never create a duplicate
    risk_assessment/crisis_event/alert chain -- closing the dedup gap noted in
    the Phase 5-6 report (TM-09), now that a real messages table exists.

    emotion_model is observability only (see ml/MODEL_CARD.md): its prediction
    is recorded on the risk_assessments row for future clinical review, but it
    is never passed to CrisisDetector and cannot change decision.level. A
    prediction failure is caught and simply omitted -- it must never break the
    crisis pipeline it has no authority over."""
    detector = CrisisDetector(policy, rules)
    decision = detector.evaluate(text, model)

    emotion_label = emotion_confidence = emotion_model_version = None
    if emotion_model is not None:
        try:
            prediction = top_prediction(emotion_model, text)
            emotion_label, emotion_confidence, emotion_model_version = prediction.label, prediction.confidence, emotion_model.version
        except Exception:
            LOGGER.exception("emotion model prediction failed; continuing without it")

    risk_assessment_id = str(uuid4())
    now = utc_now().isoformat()
    conn.execute(
        "INSERT INTO risk_assessments(id,patient_id,input_reference,score,confidence,model_version,model_available,"
        "emotion_label,emotion_confidence,emotion_model_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (risk_assessment_id, patient_id, message_reference, decision.score, decision.confidence,
         decision.model_version, int(decision.model_available),
         emotion_label, emotion_confidence, emotion_model_version, now),
    )

    crisis_event_id = str(uuid4())
    conn.execute(
        "INSERT INTO crisis_events(id,risk_assessment_id,patient_id,level,reasons,rules_version,policy_version,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (crisis_event_id, risk_assessment_id, patient_id, decision.level, ",".join(decision.reasons),
         decision.rules_version, decision.policy_version, now),
    )

    if decision.level not in ALERT_LEVELS_REQUIRING_ALERT:
        return MessageOutcome(decision, crisis_event_id, None, False, ())

    alert, created = open_alert(conn, patient_id, crisis_event_id, decision, message_reference)
    outcomes = tuple(notify_alert(conn, alert, policy.notification_channels, provider, request_id)) if created else ()
    return MessageOutcome(decision, crisis_event_id, alert, created, outcomes)
