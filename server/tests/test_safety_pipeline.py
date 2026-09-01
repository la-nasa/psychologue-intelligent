"""Pipeline risque -> crise -> alerte -> notification, async + tenant.
Porté de v1 `tests/test_crisis_pipeline.py::PipelineIntegrationTests`."""
from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application.notifications import LogNotificationProvider
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.db import tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Alert, CrisisEvent, Notification, RiskAssessment

_DIR = Path("config/policies")
_BASE = SafetyConfig(
    policy=load_crisis_policy(_DIR / "crisis-policy-v1.json"),
    rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
    templates=load_response_templates(_DIR / "response-templates-v1.json"),
)


def _with_channels(*channels: str) -> SafetyConfig:
    return dataclasses.replace(_BASE, policy=dataclasses.replace(_BASE.policy, notification_channels=channels))


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.fixture
async def patient(make_org, make_user):
    org_id = await make_org()
    patient_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    return org_id, patient_id


async def test_red_message_opens_alert_and_records_the_full_trail(patient) -> None:
    org_id, patient_id = patient
    async with tenant_session(org_id) as session:
        outcome = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="J'ai un plan suicidaire", message_reference="msg-1",
            config=_BASE, risk_model=KeywordRiskModel(), notification_provider=LogNotificationProvider(),
            request_id="req-1",
        )
        assert outcome.decision.level == "RED"
        assert outcome.alert_created is True
        assert await _count(session, RiskAssessment) == 1
        assert await _count(session, CrisisEvent) == 1
        assert await _count(session, Alert) == 1
        # aucun canal configuré dans la politique par défaut -> honnêtement "skipped", jamais feint "sent"
        assert len(outcome.notifications) == 1
        assert outcome.notifications[0].status == "SKIPPED_NO_CHANNEL"


async def test_green_message_never_opens_an_alert(patient) -> None:
    org_id, patient_id = patient
    async with tenant_session(org_id) as session:
        outcome = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="Ma seance de sport s'est bien passee", message_reference="msg-2",
            config=_BASE, risk_model=KeywordRiskModel(), notification_provider=LogNotificationProvider(),
            request_id="req-2",
        )
        assert outcome.decision.level == "GREEN"
        assert outcome.alert_id is None
        assert await _count(session, Alert) == 0
        assert await _count(session, CrisisEvent) == 1  # la trace est toujours écrite


async def test_retried_message_reference_does_not_duplicate_alert_or_notification(patient) -> None:
    org_id, patient_id = patient
    for _ in range(2):
        async with tenant_session(org_id) as session:
            await evaluate_incoming_message(
                session, organization_id=org_id, patient_id=patient_id,
                text="plan suicidaire", message_reference="msg-3",
                config=_with_channels("clinician-console"), risk_model=KeywordRiskModel(),
                notification_provider=LogNotificationProvider(), request_id="req-3",
            )
    async with tenant_session(org_id) as session:
        assert await _count(session, Alert) == 1
        assert await _count(session, Notification) == 1


async def test_notification_uses_configured_channel_when_present(patient) -> None:
    org_id, patient_id = patient
    async with tenant_session(org_id) as session:
        outcome = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="plan suicidaire", message_reference="msg-4",
            config=_with_channels("clinician-console"), risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), request_id="req-4",
        )
    assert len(outcome.notifications) == 1
    assert outcome.notifications[0].status == "SENT"
    assert outcome.notifications[0].provider_ref is not None


async def test_alert_carries_sla_due_at_from_policy(patient) -> None:
    org_id, patient_id = patient
    async with tenant_session(org_id) as session:
        outcome = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="plan suicidaire", message_reference="msg-5",
            config=_with_channels("clinician-console"), risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), request_id="req-5",
        )
        alert = (await session.execute(select(Alert).where(Alert.id == outcome.alert_id))).scalar_one()
        assert alert.sla_due_at is not None
        assert alert.sla_due_at > dt.datetime.now(dt.UTC)
