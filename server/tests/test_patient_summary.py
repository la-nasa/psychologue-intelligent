"""PatientSummaryService + Evidence (Phase 13).

Le critère de sortie : **chaque affirmation de la synthèse renvoie à une source
réelle rattachée au patient**, vérifié ici en résolvant chaque pièce
justificative. Plus : jamais de diagnostic, jamais de contenu déchiffré.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application import clinician, consent, goals, memory, relationships
from app.application.notifications import LogNotificationProvider
from app.application.patient_summary import DISCLAIMER, Evidence, build_summary, resolve_evidence
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.crypto import encrypt
from app.core.db import system_session, tenant_session
from app.core.errors import PermissionDeniedError
from app.core.security import _totp_at, new_totp_secret
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Conversation, User

_DIR = Path("config/policies")

_DIAGNOSTIC_WORDS = ("diagnostic", "souffre de", "atteint de", "trouble dépressif", "dépression majeure")


def _config() -> SafetyConfig:
    policy = dataclasses.replace(load_crisis_policy(_DIR / "crisis-policy-v1.json"), notification_channels=())
    return SafetyConfig(
        policy=policy,
        rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
        templates=load_response_templates(_DIR / "response-templates-v1.json"),
    )


async def _seed_phq9(org_id: uuid.UUID, patient_id: uuid.UUID, answers: list[int], *, days_ago: int) -> None:
    from app.application import assessment

    async with tenant_session(org_id, user_id=patient_id) as session:
        res = await assessment.submit_phq9(
            session, organization_id=org_id, user_id=patient_id, answers=answers,
            config=_config(), notification_provider=LogNotificationProvider(), request_id="r",
        )
    if days_ago:
        async with system_session() as session:
            from app.infrastructure.models import Phq9Assessment

            row = (await session.execute(select(Phq9Assessment).where(Phq9Assessment.id == uuid.UUID(res["id"])))).scalar_one()
            row.completed_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=days_ago)


@pytest.fixture
async def rich_patient(make_org, make_user):
    """Patient bien garni + un clinicien référent."""
    org_id = await make_org()
    admin = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com", roles=("ADMIN",))
    patient = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    psy = await make_user(org_id, f"c-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=psy, request_id="r"
        )

    await _seed_phq9(org_id, patient, [2, 1, 1, 1, 1, 1, 1, 1, 0], days_ago=14)  # total 9, item9=0 (pas d'alerte)
    await _seed_phq9(org_id, patient, [2, 2, 2, 2, 1, 1, 1, 0, 1], days_ago=0)   # total 11, item9=1 (alerte ORANGE)

    async with tenant_session(org_id) as session:
        await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient, text="j'ai un plan suicidaire",
            message_reference=f"m-{uuid.uuid4().hex[:8]}", config=_config(), risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), request_id="r",
        )
    async with tenant_session(org_id, user_id=patient) as session:
        await consent.grant(session, organization_id=org_id, user_id=patient, purpose="CARE", request_id="r")
        gid = await goals.create_goal(
            session, organization_id=org_id, user_id=patient, title="Reprendre le sport", description="", request_id="r"
        )
        await goals.record_progress(
            session, organization_id=org_id, user_id=patient, goal_id=gid, value=40, note="", request_id="r"
        )
        await memory.remember(
            session, organization_id=org_id, user_id=patient,
            content="Le patient a mentionné un secret très personnel: SECRET-CANARY", request_id="r",
        )
        session.add(Conversation(id=uuid.uuid4(), organization_id=org_id, patient_id=patient, status="ACTIVE"))

    return org_id, admin, patient, psy


async def test_every_statement_is_backed_by_resolvable_evidence(rich_patient) -> None:
    org_id, _admin, patient, _psy = rich_patient
    async with tenant_session(org_id) as session:
        summary = await build_summary(session, patient_id=patient)

        assert summary.statements  # le patient est garni
        for stmt in summary.statements:
            assert stmt.evidence, f"{stmt.key} n'a aucune pièce justificative"
            for ev in stmt.evidence:
                resolved = await resolve_evidence(session, patient_id=patient, evidence=ev)
                assert resolved is not None, f"{stmt.key} → {ev} ne se résout pas vers une source du patient"
                assert resolved["type"] == ev.type and resolved["id"] == ev.id


async def test_evidence_of_another_patient_does_not_resolve(rich_patient, make_user) -> None:
    org_id, _admin, patient, _psy = rich_patient
    other = await make_user(org_id, f"o-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id) as session:
        summary = await build_summary(session, patient_id=patient)
        an_ev = summary.statements[0].evidence[0]
        # même identifiant, mauvais patient → None
        assert await resolve_evidence(session, patient_id=other, evidence=an_ev) is None
        # identifiant inconnu → None
        assert await resolve_evidence(
            session, patient_id=patient, evidence=Evidence(type="alert", id=str(uuid.uuid4()))
        ) is None


async def test_summary_is_correlational_never_diagnostic(rich_patient) -> None:
    org_id, _admin, patient, _psy = rich_patient
    async with tenant_session(org_id) as session:
        summary = await build_summary(session, patient_id=patient)
    blob = " ".join(s.text for s in summary.statements).lower()
    for word in _DIAGNOSTIC_WORDS:
        assert word not in blob, f"formulation diagnostique interdite : {word!r}"
    assert summary.disclaimer == DISCLAIMER


async def test_summary_never_carries_decrypted_content(rich_patient) -> None:
    org_id, _admin, patient, _psy = rich_patient
    async with tenant_session(org_id) as session:
        summary = await build_summary(session, patient_id=patient)
    blob = repr(summary.to_dict())
    assert "SECRET-CANARY" not in blob          # contenu de mémoire
    assert "plan suicidaire" not in blob         # contenu de message
    assert "answers" not in blob and "_enc" not in blob


async def test_item9_and_trend_statements_are_conditional(make_org, make_user) -> None:
    org_id = await make_org()
    patient = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    # un seul PHQ-9, item 9 = 0 → ni "trend" ni "item9"
    await _seed_phq9(org_id, patient, [1, 1, 1, 0, 0, 0, 0, 0, 0], days_ago=0)
    async with tenant_session(org_id) as session:
        keys = {s.key for s in (await build_summary(session, patient_id=patient)).statements}
    assert "phq9.latest" in keys
    assert "phq9.trend" not in keys and "phq9.item9" not in keys


async def test_empty_patient_yields_only_the_disclaimer(make_org, make_user) -> None:
    org_id = await make_org()
    patient = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id) as session:
        summary = await build_summary(session, patient_id=patient)
    assert summary.statements == ()
    assert summary.disclaimer == DISCLAIMER


# --- Patient 360 --------------------------------------------------------- #


async def test_patient_360_requires_a_relationship(rich_patient, make_user) -> None:
    org_id, _admin, patient, _psy = rich_patient
    stranger = await make_user(org_id, f"s-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=stranger) as session:
        with pytest.raises(PermissionDeniedError):
            await clinician.patient_360(session, clinician_id=stranger, patient_id=patient)


async def test_patient_360_bundles_summary_consents_goals_and_timeline(rich_patient) -> None:
    org_id, _admin, patient, psy = rich_patient
    async with tenant_session(org_id, user_id=psy) as session:
        record = await clinician.patient_360(session, clinician_id=psy, patient_id=patient)
    assert record["summary"]["statements"]
    assert any(c["purpose"] == "CARE" and c["active"] for c in record["consents"])
    assert record["goals"][0]["title"] == "Reprendre le sport"
    # une alerte message (RED) + une alerte PHQ-9 item-9 (ORANGE)
    assert {a["level"] for a in record["alerts"]} == {"RED", "ORANGE"}
    assert "SECRET-CANARY" not in repr(record)


# --- RBAC / HTTP -------------------------------------------------------- #


async def test_patient_cannot_read_a_summary(client: AsyncClient, make_org) -> None:
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
    assert (await client.get(f"/api/v1/clinician/patients/{uuid.uuid4()}/summary", headers=h)).status_code == 403
    assert (await client.get(f"/api/v1/clinician/patients/{uuid.uuid4()}/360", headers=h)).status_code == 403


async def test_clinician_reads_summary_then_opens_each_evidence(client: AsyncClient, rich_patient) -> None:
    org_id, _admin, patient, psy = rich_patient
    secret = new_totp_secret()
    async with system_session() as session:
        row = (await session.execute(select(User).where(User.id == psy))).scalar_one()
        row.mfa_secret_enc = encrypt(secret)
        row.mfa_enabled = True
    slug = (await _org_slug(org_id))
    login = await client.post(
        "/api/v1/auth/sessions",
        json={
            "organization_slug": slug, "email": await _email_of(psy),
            "password": "correct-horse-staple-42", "totp_code": _totp_at(secret, int(time.time()) // 30),
        },
    )
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    summary = (await client.get(f"/api/v1/clinician/patients/{patient}/summary", headers=h)).json()
    assert summary["disclaimer"] == DISCLAIMER
    assert summary["statements"]
    for stmt in summary["statements"]:
        for ev in stmt["evidence"]:
            resp = await client.get(
                f"/api/v1/clinician/patients/{patient}/evidence/{ev['type']}/{ev['id']}", headers=h
            )
            assert resp.status_code == 200

    full = await client.get(f"/api/v1/clinician/patients/{patient}/360", headers=h)
    assert full.status_code == 200 and full.json()["summary"]["statements"]


async def _org_slug(org_id: uuid.UUID) -> str:
    from app.infrastructure.models import Organization

    async with system_session() as session:
        return (await session.execute(select(Organization.slug).where(Organization.id == org_id))).scalar_one()


async def _email_of(user_id: uuid.UUID) -> str:
    async with system_session() as session:
        return (await session.execute(select(User.email_normalized).where(User.id == user_id))).scalar_one()
