"""Worker périodique : `run_once` enchaîne sla_sweep + retry_notifications +
reminders, sur une session système, de façon idempotente."""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application import assessment
from app.application.notifications import LogNotificationProvider
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.db import system_session, tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Alert, AssessmentReminder
from app.workers.scheduler import run_once

_DIR = Path("config/policies")
_CONFIG = SafetyConfig(
    policy=load_crisis_policy(_DIR / "crisis-policy-v1.json"),
    rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
    templates=load_response_templates(_DIR / "response-templates-v1.json"),
)


@pytest.fixture
async def patient(make_org, make_user):
    org_id = await make_org()
    pid = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    return org_id, pid


async def test_run_once_is_a_noop_when_nothing_is_due() -> None:
    assert await run_once() == {"sla_escalated": 0, "notifications_retried": 0, "reminders_sent": 0}


async def test_run_once_escalates_overdue_alerts_and_sends_due_reminders(patient) -> None:
    org_id, pid = patient
    # une alerte RED (pas de canal -> reste OPEN, avec SLA)
    async with tenant_session(org_id) as session:
        out = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=pid, text="plan suicidaire",
            message_reference=f"m-{uuid.uuid4().hex[:8]}", config=_CONFIG, risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), request_id="r",
        )
    # un rappel PHQ-9 déjà échu (inséré directement)
    async with system_session() as session:
        session.add(
            AssessmentReminder(
                id=uuid.uuid4(), organization_id=org_id, user_id=pid, instrument="PHQ-9",
                due_at=dt.datetime.now(dt.UTC) - dt.timedelta(hours=1), status="PENDING",
            )
        )

    # forcer l'échéance SLA en la ramenant dans le passé
    async with system_session() as session:
        await session.execute(
            update(Alert).where(Alert.id == out.alert_id).values(
                sla_due_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
            )
        )

    result = await run_once()
    assert result["sla_escalated"] == 1
    assert result["reminders_sent"] == 1

    async with system_session() as session:
        assert (await session.execute(select(Alert.status).where(Alert.id == out.alert_id))).scalar_one() == "ESCALATED"
        assert (await session.execute(select(AssessmentReminder.status))).scalar_one() == "SENT"

    # idempotent
    assert await run_once() == {"sla_escalated": 0, "notifications_retried": 0, "reminders_sent": 0}


async def test_reminder_worker_via_submit_then_due(patient) -> None:
    org_id, pid = patient
    async with tenant_session(org_id, user_id=pid) as session:
        rid = await assessment.schedule_reminder(
            session, organization_id=org_id, user_id=pid,
            due_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=7), request_id="r",
        )
        # ramener l'échéance dans le passé
        await session.execute(
            update(AssessmentReminder).where(AssessmentReminder.id == rid).values(
                due_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
            )
        )
    assert (await run_once())["reminders_sent"] == 1
