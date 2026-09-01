"""Plateforme clinicien (master prompt §33) : Today's Overview, Patient List,
Alert Center, timeline patient, actions sur alerte — toutes bornées par la
relation `ACTIVE` patient-clinicien. RBAC deny-by-default : un `PATIENT`
n'atteint jamais ces endpoints."""
from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application import clinician, relationships
from app.application.alerts import act_on_alert
from app.application.notifications import LogNotificationProvider
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.crypto import encrypt
from app.core.db import system_session, tenant_session
from app.core.errors import DomainError, PermissionDeniedError
from app.core.security import _totp_at, new_totp_secret
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Alert, AuditLog, User

_DIR = Path("config/policies")


def _config(*channels: str) -> SafetyConfig:
    policy = load_crisis_policy(_DIR / "crisis-policy-v1.json")
    policy = dataclasses.replace(policy, notification_channels=channels)
    return SafetyConfig(
        policy=policy,
        rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
        templates=load_response_templates(_DIR / "response-templates-v1.json"),
    )


async def _raise_alert(org_id: uuid.UUID, patient_id: uuid.UUID, text: str) -> uuid.UUID:
    async with tenant_session(org_id) as session:
        out = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id, text=text,
            message_reference=f"m-{uuid.uuid4().hex[:8]}", config=_config(), risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), request_id="r",
        )
    return out.alert_id


@pytest.fixture
async def followed(make_org, make_user):
    """Un patient suivi par un clinicien, avec une alerte RED ouverte."""
    org_id = await make_org()
    admin = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com", roles=("ADMIN",))
    patient = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    clinician_id = await make_user(org_id, f"c-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin,
            patient_id=patient, clinician_id=clinician_id, request_id="r",
        )
    alert_id = await _raise_alert(org_id, patient, "j'ai un plan suicidaire")
    return org_id, admin, patient, clinician_id, alert_id


# --- accès borné par la relation ------------------------------------------- #


async def test_timeline_requires_an_active_relationship(followed, make_user) -> None:
    org_id, _admin, patient, clinician_id, _alert_id = followed
    stranger = await make_user(org_id, f"s-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=stranger) as session:
        with pytest.raises(PermissionDeniedError):
            await clinician.patient_timeline(session, clinician_id=stranger, patient_id=patient)
    # le clinicien référent, lui, voit le dossier
    async with tenant_session(org_id, user_id=clinician_id) as session:
        timeline = await clinician.patient_timeline(session, clinician_id=clinician_id, patient_id=patient)
    assert timeline["patient_id"] == str(patient)
    assert len(timeline["alerts"]) == 1


async def test_timeline_never_carries_conversation_content_or_raw_answers(followed) -> None:
    org_id, _admin, patient, clinician_id, _alert_id = followed
    async with tenant_session(org_id, user_id=patient) as session:
        from app.application import assessment

        await assessment.submit_phq9(
            session, organization_id=org_id, user_id=patient, answers=[2, 2, 2, 2, 1, 1, 1, 0, 0],
            config=_config(), notification_provider=LogNotificationProvider(), request_id="r",
        )
    async with tenant_session(org_id, user_id=clinician_id) as session:
        timeline = await clinician.patient_timeline(session, clinician_id=clinician_id, patient_id=patient)
    blob = repr(timeline)
    assert "plan suicidaire" not in blob
    assert "answers" not in blob and "answers_enc" not in blob
    # la bande de sévérité est là, la réponse brute non
    assert timeline["phq9_history"][0]["severity_band"]


async def test_lists_are_scoped_to_followed_patients(followed, make_user) -> None:
    org_id, _admin, patient, clinician_id, _alert_id = followed
    # un second patient NON suivi par ce clinicien, avec une alerte
    other = await make_user(org_id, f"o-{uuid.uuid4().hex[:6]}@x.example.com")
    await _raise_alert(org_id, other, "j'ai un plan suicidaire")

    async with tenant_session(org_id, user_id=clinician_id) as session:
        patients = await clinician.list_patients(session, clinician_id=clinician_id)
        alerts = await clinician.list_alerts(session, clinician_id=clinician_id)
    assert [p["patient_id"] for p in patients] == [str(patient)]
    assert {a["patient_id"] for a in alerts} == {str(patient)}


async def test_overview_counts_only_this_clinicians_queue(followed) -> None:
    org_id, _admin, _patient, clinician_id, _alert_id = followed
    async with tenant_session(org_id, user_id=clinician_id) as session:
        ov = await clinician.overview(session, clinician_id=clinician_id)
    assert ov["patients_followed"] == 1
    assert ov["open_alerts"]["total"] == 1 and ov["open_alerts"]["red"] == 1
    assert ov["assigned_to_me"] == 0


async def test_alert_filters_reject_unknown_values(followed) -> None:
    org_id, _admin, _patient, clinician_id, _alert_id = followed
    async with tenant_session(org_id, user_id=clinician_id) as session:
        with pytest.raises(DomainError):
            await clinician.list_alerts(session, clinician_id=clinician_id, level="PURPLE")
        with pytest.raises(DomainError):
            await clinician.list_alerts(session, clinician_id=clinician_id, status="NUKED")


# --- actions sur alerte ---------------------------------------------------- #


async def test_act_on_alert_acknowledges_assigns_and_audits(followed) -> None:
    org_id, _admin, _patient, clinician_id, alert_id = followed
    async with tenant_session(org_id, user_id=clinician_id) as session:
        updated = await act_on_alert(
            session, organization_id=org_id, clinician_id=clinician_id, alert_id=alert_id,
            target="ACKNOWLEDGED", justification="pris en charge", request_id="r",
        )
    assert updated.status == "ACKNOWLEDGED"
    async with tenant_session(org_id) as session:
        alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one()
        assert str(alert.assigned_clinician_id) == str(clinician_id)
        assert alert.acknowledged_at is not None
    async with system_session() as session:
        actions = (await session.execute(select(AuditLog.action))).scalars().all()
    assert "alert.act" in actions


async def test_act_on_alert_denied_without_relationship(followed, make_user) -> None:
    org_id, _admin, _patient, _clinician_id, alert_id = followed
    stranger = await make_user(org_id, f"s-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=stranger) as session:
        with pytest.raises(PermissionDeniedError):
            await act_on_alert(
                session, organization_id=org_id, clinician_id=stranger, alert_id=alert_id,
                target="ACKNOWLEDGED", justification="x", request_id="r",
            )


async def test_act_on_alert_rejects_an_invalid_transition(followed) -> None:
    org_id, _admin, _patient, clinician_id, alert_id = followed
    async with tenant_session(org_id, user_id=clinician_id) as session:
        with pytest.raises(DomainError):
            await act_on_alert(
                session, organization_id=org_id, clinician_id=clinician_id, alert_id=alert_id,
                target="RESOLVED", justification="trop tôt", request_id="r",
            )


async def test_concurrent_acks_have_exactly_one_winner(followed) -> None:
    org_id, _admin, _patient, clinician_id, alert_id = followed

    async def go() -> str:
        async with tenant_session(org_id, user_id=clinician_id) as session:
            await act_on_alert(
                session, organization_id=org_id, clinician_id=clinician_id, alert_id=alert_id,
                target="ACKNOWLEDGED", justification="course", request_id="r",
            )
        return "ok"

    results = await asyncio.gather(go(), go(), return_exceptions=True)
    winners = [r for r in results if r == "ok"]
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(winners) == 1
    assert len(losers) == 1 and isinstance(losers[0], DomainError)


# --- RBAC HTTP ----------------------------------------------------------- #


async def test_patient_cannot_reach_clinician_endpoints(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post(
        "/api/v1/auth/register",
        json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"},
    )
    r = await client.post(
        "/api/v1/auth/sessions",
        json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"},
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for path in ("/api/v1/clinician/overview", "/api/v1/clinician/patients", "/api/v1/clinician/alerts"):
        assert (await client.get(path, headers=h)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/clinician/alerts/{uuid.uuid4()}/actions",
            json={"target": "ACKNOWLEDGED", "justification": "x"}, headers=h,
        )
    ).status_code == 403


async def test_clinician_http_happy_path(client: AsyncClient, make_org, make_user) -> None:
    org_id = await make_org("clinic")
    admin = await make_user(org_id, "admin@clinic.example.com", roles=("ADMIN",))
    patient = await make_user(org_id, "pat@clinic.example.com")
    psy = await make_user(org_id, "psy@clinic.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=psy, request_id="r"
        )
    alert_id = await _raise_alert(org_id, patient, "j'ai un plan suicidaire")

    # provisionnement MFA (les rôles cliniques l'exigent — cf. test_mfa)
    secret = new_totp_secret()
    async with system_session() as session:
        row = (await session.execute(select(User).where(User.id == psy))).scalar_one()
        row.mfa_secret_enc = encrypt(secret)
        row.mfa_enabled = True
    login = await client.post(
        "/api/v1/auth/sessions",
        json={
            "organization_slug": "clinic", "email": "psy@clinic.example.com",
            "password": "correct-horse-staple-42", "totp_code": _totp_at(secret, int(time.time()) // 30),
        },
    )
    assert login.status_code == 201
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    ov = (await client.get("/api/v1/clinician/overview", headers=h)).json()
    assert ov["open_alerts"]["red"] == 1

    patients = (await client.get("/api/v1/clinician/patients", headers=h)).json()["items"]
    assert patients[0]["patient_id"] == str(patient)

    alerts = (await client.get("/api/v1/clinician/alerts?level=RED", headers=h)).json()["items"]
    assert alerts[0]["id"] == str(alert_id)

    acted = await client.post(
        f"/api/v1/clinician/alerts/{alert_id}/actions",
        json={"target": "ACKNOWLEDGED", "justification": "vu"}, headers=h,
    )
    assert acted.status_code == 200 and acted.json()["status"] == "ACKNOWLEDGED"

    timeline = (await client.get(f"/api/v1/clinician/patients/{patient}/timeline", headers=h)).json()
    assert timeline["alerts"][0]["status"] == "ACKNOWLEDGED"
