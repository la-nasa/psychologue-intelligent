"""Clinician AI Review (Phase 14) : décision + notes 1-5 + catégorie, borné par
la relation patient-clinicien, **usage non punitif** (aucune agrégation par
relecteur). Voir `docs/governance/ai-review-non-punitive.md`."""
from __future__ import annotations

import inspect
import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.application import ai_review, relationships
from app.core.crypto import encrypt
from app.core.db import system_session, tenant_session
from app.core.errors import ConflictError, DomainError, PermissionDeniedError
from app.core.security import _totp_at, new_totp_secret
from app.infrastructure.models import AuditLog, ClinicianResponseReview, Conversation, Message, Organization, User

_GOOD_SCORES = dict.fromkeys(ai_review.SCORE_DIMENSIONS, 4)


async def _seed_conversation(org_id: uuid.UUID, patient_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Une conversation avec un message patient puis une réponse assistant."""
    conv_id, patient_msg, assistant_msg = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with system_session() as session:
        session.add(Conversation(id=conv_id, organization_id=org_id, patient_id=patient_id, status="ACTIVE"))
        session.add(Message(
            id=patient_msg, organization_id=org_id, conversation_id=conv_id, author_type="PATIENT",
            content_enc=encrypt("je me sens un peu mieux cette semaine") or "", sequence_no=1,
        ))
        session.add(Message(
            id=assistant_msg, organization_id=org_id, conversation_id=conv_id, author_type="ASSISTANT",
            content_enc=encrypt("C'est encourageant. Qu'est-ce qui a aidé, selon vous ?") or "", sequence_no=2,
            responder_version="local-supportive-1", generation_path="FAST",
        ))
    return conv_id, assistant_msg


@pytest.fixture
async def followed(make_org, make_user):
    org_id = await make_org()
    admin = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com", roles=("ADMIN",))
    patient = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    # rôles cliniques : traite ET peut consulter le rapport qualité (superviseur)
    psy = await make_user(
        org_id, f"c-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST", "CLINICAL_SUPERVISOR")
    )
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=psy, request_id="r"
        )
    _conv, assistant_msg = await _seed_conversation(org_id, patient)
    return org_id, admin, patient, psy, assistant_msg


# --- soumission -------------------------------------------------------- #


async def test_approve_review_persists_scores_and_model_version(followed) -> None:
    org_id, _admin, _patient, psy, msg = followed
    async with tenant_session(org_id, user_id=psy) as session:
        rid = await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy, message_id=msg,
            decision="APPROVE", scores=_GOOD_SCORES, feedback_category="RELEVANCE", request_id="r",
        )
    async with system_session() as session:
        row = (await session.execute(select(ClinicianResponseReview).where(ClinicianResponseReview.id == rid))).scalar_one()
    assert row.decision == "APPROVE"
    assert row.scores_json == _GOOD_SCORES
    assert row.model_version == "local-supportive-1"
    assert row.corrected_response_enc is None


async def test_scores_must_cover_every_dimension_within_range(followed) -> None:
    org_id, _admin, _patient, psy, msg = followed
    async with tenant_session(org_id, user_id=psy) as session:
        with pytest.raises(DomainError):
            await ai_review.submit_review(
                session, organization_id=org_id, reviewer_id=psy, message_id=msg,
                decision="APPROVE", scores={"empathy": 4}, feedback_category="TONE", request_id="r",
            )
        with pytest.raises(DomainError):
            await ai_review.submit_review(
                session, organization_id=org_id, reviewer_id=psy, message_id=msg,
                decision="APPROVE", scores={**_GOOD_SCORES, "safety": 9}, feedback_category="TONE", request_id="r",
            )


async def test_edit_requires_a_corrected_response(followed) -> None:
    org_id, _admin, _patient, psy, msg = followed
    async with tenant_session(org_id, user_id=psy) as session:
        with pytest.raises(DomainError):
            await ai_review.submit_review(
                session, organization_id=org_id, reviewer_id=psy, message_id=msg,
                decision="EDIT", scores=_GOOD_SCORES, feedback_category="TONE", request_id="r",
            )
        rid = await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy, message_id=msg,
            decision="EDIT", scores=_GOOD_SCORES, feedback_category="TONE",
            corrected_response="Reformulation plus chaleureuse.", request_id="r",
        )
    async with system_session() as session:
        row = (await session.execute(select(ClinicianResponseReview).where(ClinicianResponseReview.id == rid))).scalar_one()
    assert row.corrected_response_enc is not None


async def test_only_an_assistant_message_can_be_reviewed(followed) -> None:
    org_id, _admin, _patient, psy, _msg = followed
    async with system_session() as session:
        patient_msg = (
            await session.execute(select(Message.id).where(Message.author_type == "PATIENT"))
        ).scalars().first()
    async with tenant_session(org_id, user_id=psy) as session:
        with pytest.raises(DomainError):
            await ai_review.submit_review(
                session, organization_id=org_id, reviewer_id=psy, message_id=patient_msg,
                decision="APPROVE", scores=_GOOD_SCORES, feedback_category="TONE", request_id="r",
            )


async def test_review_requires_an_active_relationship(followed, make_user) -> None:
    org_id, _admin, _patient, _psy, msg = followed
    stranger = await make_user(org_id, f"s-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=stranger) as session:
        with pytest.raises(PermissionDeniedError):
            await ai_review.submit_review(
                session, organization_id=org_id, reviewer_id=stranger, message_id=msg,
                decision="APPROVE", scores=_GOOD_SCORES, feedback_category="TONE", request_id="r",
            )


async def test_one_review_per_message_per_reviewer(followed, make_user) -> None:
    org_id, admin, patient, psy, msg = followed
    async with tenant_session(org_id, user_id=psy) as session:
        await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy, message_id=msg,
            decision="APPROVE", scores=_GOOD_SCORES, feedback_category="TONE", request_id="r",
        )
    async with tenant_session(org_id, user_id=psy) as session:
        with pytest.raises(ConflictError):
            await ai_review.submit_review(
                session, organization_id=org_id, reviewer_id=psy, message_id=msg,
                decision="REJECT", scores=_GOOD_SCORES, feedback_category="TONE", request_id="r",
            )
    # un autre clinicien référent peut, lui, ajouter sa propre revue
    psy2 = await make_user(org_id, f"c2-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=psy2, request_id="r"
        )
    async with tenant_session(org_id, user_id=psy2) as session:
        await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy2, message_id=msg,
            decision="APPROVE", scores=_GOOD_SCORES, feedback_category="TONE", request_id="r",
        )
    async with system_session() as session:
        count = len((await session.execute(select(ClinicianResponseReview))).scalars().all())
    assert count == 2


async def test_safety_flag_is_recorded_and_listed(followed) -> None:
    org_id, _admin, _patient, psy, msg = followed
    async with tenant_session(org_id, user_id=psy) as session:
        await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy, message_id=msg,
            decision="FLAG_SAFETY", scores=_GOOD_SCORES, feedback_category="SAFETY",
            clinical_comment="Minimise un propos inquiétant.", request_id="r",
        )
    async with system_session() as session:
        actions = (await session.execute(select(AuditLog.action))).scalars().all()
        flags = await ai_review.list_safety_flags(session)
    assert "ai_review.safety_flag" in actions
    assert len(flags) == 1 and flags[0]["message_id"] == str(msg)


# --- gouvernance : usage non punitif --------------------------------- #


async def test_quality_report_aggregates_by_model_not_reviewer(followed, make_user) -> None:
    org_id, admin, patient, psy, msg = followed
    psy2 = await make_user(org_id, f"c2-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=psy2, request_id="r"
        )
    async with tenant_session(org_id, user_id=psy) as session:
        await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy, message_id=msg,
            decision="APPROVE", scores=dict.fromkeys(ai_review.SCORE_DIMENSIONS, 5),
            feedback_category="RELEVANCE", request_id="r",
        )
    async with tenant_session(org_id, user_id=psy2) as session:
        await ai_review.submit_review(
            session, organization_id=org_id, reviewer_id=psy2, message_id=msg,
            decision="REJECT", scores=dict.fromkeys(ai_review.SCORE_DIMENSIONS, 2),
            feedback_category="CLINICAL_ACCURACY", request_id="r",
        )
    async with tenant_session(org_id, user_id=psy) as session:
        report = await ai_review.model_quality_report(session, model_version="local-supportive-1")

    assert report["review_count"] == 2
    assert report["by_decision"]["APPROVE"] == 1 and report["by_decision"]["REJECT"] == 1
    assert report["mean_scores"]["empathy"] == 3.5
    assert report["approval_rate"] == 0.5
    # aucun identifiant de relecteur nulle part dans la sortie
    blob = str(report)
    assert str(psy) not in blob and str(psy2) not in blob


def test_module_exposes_no_per_reviewer_aggregation() -> None:
    # `model_quality_report` ne prend pas de paramètre relecteur
    params = set(inspect.signature(ai_review.model_quality_report).parameters)
    assert params <= {"session", "model_version", "since"}
    # aucune fonction publique ne suggère une statistique par clinicien
    banned = ("per_reviewer", "reviewer_stat", "clinician_perf", "by_reviewer", "reviewer_scorecard")
    for name in dir(ai_review):
        assert not any(b in name.lower() for b in banned), name


# --- RBAC / HTTP ---------------------------------------------------- #


async def test_patient_cannot_touch_ai_review(client: AsyncClient, make_org) -> None:
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
    assert (await client.get(f"/api/v1/clinician/ai-review/patients/{uuid.uuid4()}/messages", headers=h)).status_code == 403
    assert (await client.get("/api/v1/clinician/ai-review/quality-report", headers=h)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/clinician/ai-review/messages/{uuid.uuid4()}/review",
            json={"decision": "APPROVE", "scores": _GOOD_SCORES, "feedback_category": "TONE"}, headers=h,
        )
    ).status_code == 403


async def test_clinician_http_review_flow(client: AsyncClient, followed) -> None:
    org_id, _admin, patient, psy, msg = followed
    secret = new_totp_secret()
    async with system_session() as session:
        row = (await session.execute(select(User).where(User.id == psy))).scalar_one()
        row.mfa_secret_enc = encrypt(secret)
        row.mfa_enabled = True
        slug = (await session.execute(select(Organization.slug).where(Organization.id == org_id))).scalar_one()
        email = row.email_normalized
    login = await client.post(
        "/api/v1/auth/sessions",
        json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42",
              "totp_code": _totp_at(secret, int(time.time()) // 30)},
    )
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = (await client.get(f"/api/v1/clinician/ai-review/patients/{patient}/messages", headers=h)).json()["items"]
    assert listed[0]["message_id"] == str(msg)
    assert listed[0]["patient_message"] and listed[0]["reviewed"] is False

    created = await client.post(
        f"/api/v1/clinician/ai-review/messages/{msg}/review",
        json={"decision": "EDIT", "scores": _GOOD_SCORES, "feedback_category": "PERSONALIZATION",
              "corrected_response": "Version mieux ajustée au profil."}, headers=h,
    )
    assert created.status_code == 201

    reviews = (await client.get(f"/api/v1/clinician/ai-review/messages/{msg}/reviews", headers=h)).json()["items"]
    assert reviews[0]["decision"] == "EDIT" and reviews[0]["corrected_response"]

    report = (await client.get("/api/v1/clinician/ai-review/quality-report", headers=h)).json()
    assert report["review_count"] == 1


def test_module_documents_the_non_punitive_rule() -> None:
    doc = (ai_review.__doc__ or "").lower()
    assert "non punitif" in doc
    assert "ai-review-non-punitive.md" in doc
