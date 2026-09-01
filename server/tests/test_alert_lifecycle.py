"""Cycle de vie d'alerte (master prompt §32) : état NOTIFIED automatique,
balayage SLA -> auto-escalade."""
from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application.alerting import sla_sweep
from app.application.alerts import transition_alert
from app.application.notifications import LogNotificationProvider
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.db import tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Alert, AlertAction

_DIR = Path("config/policies")


def _config(*channels: str, sla_minutes: dict | None = None) -> SafetyConfig:
    policy = load_crisis_policy(_DIR / "crisis-policy-v1.json")
    policy = dataclasses.replace(policy, notification_channels=channels)
    if sla_minutes is not None:
        policy = dataclasses.replace(policy, response_sla_minutes=sla_minutes)
    return SafetyConfig(
        policy=policy,
        rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
        templates=load_response_templates(_DIR / "response-templates-v1.json"),
    )


@pytest.fixture
async def patient(make_org, make_user):
    org_id = await make_org()
    pid = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    return org_id, pid


async def _raise_red(org_id, pid, config) -> uuid.UUID:
    async with tenant_session(org_id) as session:
        out = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=pid, text="plan suicidaire",
            message_reference=f"m-{uuid.uuid4().hex[:8]}", config=config, risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), request_id="r",
        )
    return out.alert_id


async def test_alert_becomes_notified_when_a_channel_confirms_send(patient) -> None:
    org_id, pid = patient
    aid = await _raise_red(org_id, pid, _config("clinician-console"))
    async with tenant_session(org_id) as session:
        alert = (await session.execute(select(Alert).where(Alert.id == aid))).scalar_one()
        assert alert.status == "NOTIFIED"
        actions = (await session.execute(select(AlertAction).where(AlertAction.alert_id == aid))).scalars().all()
        assert [a.action for a in actions] == ["NOTIFIED"]
        assert actions[0].actor_id is None  # transition système


async def test_alert_stays_open_when_no_channel_is_configured(patient) -> None:
    org_id, pid = patient
    aid = await _raise_red(org_id, pid, _config())  # aucun canal
    async with tenant_session(org_id) as session:
        assert (await session.execute(select(Alert.status).where(Alert.id == aid))).scalar_one() == "OPEN"


async def test_sla_sweep_auto_escalates_overdue_alerts(patient) -> None:
    org_id, pid = patient
    aid = await _raise_red(org_id, pid, _config("clinician-console", sla_minutes={"RED": 30, "ORANGE": 240}))

    # avant l'échéance : rien
    async with tenant_session(org_id) as session:
        assert await sla_sweep(session) == []

    # après l'échéance
    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    async with tenant_session(org_id) as session:
        escalated = await sla_sweep(session, now=later)
        assert escalated == [aid]
        alert = (await session.execute(select(Alert).where(Alert.id == aid))).scalar_one()
        assert alert.status == "ESCALATED"

    # idempotent : un second passage ne re-touche rien
    async with tenant_session(org_id) as session:
        assert await sla_sweep(session, now=later + dt.timedelta(days=1)) == []


async def test_sla_sweep_leaves_acknowledged_alerts_alone(patient, make_user) -> None:
    org_id, pid = patient
    clinician = await make_user(org_id, f"c-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    aid = await _raise_red(org_id, pid, _config("clinician-console"))

    async with tenant_session(org_id) as session:
        await transition_alert(session, alert_id=aid, target="ACKNOWLEDGED", actor_id=clinician, justification="vu")

    later = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    async with tenant_session(org_id) as session:
        assert await sla_sweep(session, now=later) == []
        assert (await session.execute(select(Alert.status).where(Alert.id == aid))).scalar_one() == "ACKNOWLEDGED"


async def test_full_lifecycle_path(patient, make_user) -> None:
    org_id, pid = patient
    clinician = await make_user(org_id, f"c-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    aid = await _raise_red(org_id, pid, _config("clinician-console"))
    for target in ("ACKNOWLEDGED", "IN_REVIEW", "RESOLVED", "CLOSED"):
        async with tenant_session(org_id) as session:
            updated = await transition_alert(session, alert_id=aid, target=target, actor_id=clinician, justification=target)
            assert updated.status == target
