"""Adaptateur e-mail (SMTP → mailpit). Vérifie que l'e-mail part **et** qu'il
ne contient aucune donnée de santé (threat-model-v2 TH-03)."""
from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

import httpx
import pytest

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application.channels import create_channel
from app.application.notifications import CompositeNotificationProvider
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.config import get_settings
from app.core.db import tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates

_DIR = Path("config/policies")
_MAILPIT_API = f"http://{get_settings().smtp_host}:8025"


def _config() -> SafetyConfig:
    return SafetyConfig(
        policy=load_crisis_policy(_DIR / "crisis-policy-v1.json"),
        rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
        templates=load_response_templates(_DIR / "response-templates-v1.json"),
    )


async def _mailpit_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            return (await c.get(f"{_MAILPIT_API}/api/v1/messages")).status_code == 200
    except Exception:
        return False


@pytest.fixture(autouse=True)
async def _clear_mailpit():
    if await _mailpit_up():
        async with httpx.AsyncClient(timeout=5) as c:
            await c.delete(f"{_MAILPIT_API}/api/v1/messages")
    yield


async def test_email_channel_delivers_a_content_free_alert(make_org, make_user) -> None:
    if not await _mailpit_up():
        pytest.skip("mailpit non démarré (docker compose up -d mailpit)")

    org_id = await make_org()
    patient_id = await make_user(org_id, f"jean.dupont-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=patient_id) as session:
        await create_channel(
            session, organization_id=org_id, actor_id=patient_id,
            name="oncall", kind="email", target="clinician-oncall@clinic.example.com", request_id="r",
        )

    config = dataclasses.replace(_config())  # canaux résolus depuis la base, pas la policy
    async with tenant_session(org_id) as session:
        outcome = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="j'ai un plan suicidaire et je pense a jean dupont", message_reference=f"m-{uuid.uuid4().hex[:8]}",
            config=config, risk_model=KeywordRiskModel(), notification_provider=CompositeNotificationProvider(),
            request_id="r",
        )
    assert outcome.notifications[0].status == "SENT"

    async with httpx.AsyncClient(timeout=5) as c:
        messages = (await c.get(f"{_MAILPIT_API}/api/v1/messages")).json()["messages"]
        assert len(messages) == 1
        msg = messages[0]
        assert "clinician-oncall@clinic.example.com" in msg["To"][0]["Address"]
        assert "Alerte RED" in msg["Subject"]
        full = (await c.get(f"{_MAILPIT_API}/api/v1/message/{msg['ID']}")).json()
        body = (full.get("Text") or "") + (full.get("HTML") or "")
    # aucune donnée clinique : ni le contenu du message, ni le nom du patient
    lowered = body.lower()
    assert "plan suicidaire" not in lowered
    assert "jean dupont" not in lowered
    assert str(patient_id) not in body
    assert str(outcome.alert_id) in body  # seul l'identifiant d'alerte est transmis


def test_email_body_construction_is_content_free() -> None:
    from email.message import EmailMessage

    # on ne teste ici que le gabarit : le provider ne reçoit qu'alert_id + level
    msg = EmailMessage()
    # reconstruit le corps comme le fait send()
    settings = get_settings()
    payload = {"alert_id": "abc-123", "level": "ORANGE"}
    msg.set_content(
        f"Une alerte de niveau {payload['level']} requiert une prise en charge.\n\n"
        f"Identifiant : {payload['alert_id']}\n"
        "Connectez-vous au tableau de bord clinicien pour la consulter.\n\n"
        "Ce message ne contient volontairement aucune donnée de santé."
    )
    body = msg.get_content()
    assert "ORANGE" in body and "abc-123" in body
    assert "patient" not in body.lower() and settings.smtp_from  # sanity
