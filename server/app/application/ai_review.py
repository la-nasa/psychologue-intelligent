"""Clinician AI Review (master prompt §38-39, audit roadmap Phase 14).

Un clinicien examine une réponse produite par l'assistant à l'un de ses patients
suivis et la note : décision (`APPROVE` / `EDIT` / `REJECT` / `FLAG_SAFETY`),
7 dimensions sur 1-5, une catégorie de retour, éventuellement une correction
proposée et un commentaire clinique.

**Usage non punitif — invariant de gouvernance.** Ces revues servent
*exclusivement* à mesurer et améliorer la qualité de l'IA (par version de
modèle, par catégorie de retour, par dimension). **Aucune** fonction de ce
module n'agrège les revues par `reviewer_id`, et `model_quality_report`
n'expose jamais d'identifiant de relecteur. Voir
`docs/governance/ai-review-non-punitive.md`. Un test vérifie ces deux points.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.application.relationships import require_active_relationship
from app.core.crypto import decrypt, encrypt
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.infrastructure.models import ClinicianResponseReview, Conversation, Message

LOGGER = logging.getLogger("pi.ai_review")

DECISIONS = ("APPROVE", "EDIT", "REJECT", "FLAG_SAFETY")
SCORE_DIMENSIONS = ("empathy", "relevance", "personalization", "context", "safety", "clarity", "usefulness")
FEEDBACK_CATEGORIES = (
    "TONE", "CLINICAL_ACCURACY", "PERSONALIZATION", "CONTEXT_UNDERSTANDING", "SAFETY", "RELEVANCE", "OTHER",
)


def _validate_scores(scores: dict) -> dict[str, int]:
    if set(scores) != set(SCORE_DIMENSIONS):
        raise DomainError(
            f"scores must cover exactly {', '.join(SCORE_DIMENSIONS)}", code="invalid_scores"
        )
    clean: dict[str, int] = {}
    for dim, value in scores.items():
        if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 5):
            raise DomainError(f"score '{dim}' must be an integer 1..5", code="invalid_scores")
        clean[dim] = value
    return clean


async def _assistant_message(session: AsyncSession, message_id: uuid.UUID) -> tuple[Message, uuid.UUID]:
    message = (
        await session.execute(select(Message).where(Message.id == message_id))
    ).scalar_one_or_none()
    if message is None:
        raise NotFoundError("message not found")
    if message.author_type != "ASSISTANT":
        raise DomainError("only an assistant response can be reviewed", code="not_reviewable")
    conversation = (
        await session.execute(select(Conversation).where(Conversation.id == message.conversation_id))
    ).scalar_one()
    return message, conversation.patient_id


async def submit_review(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    message_id: uuid.UUID,
    decision: str,
    scores: dict,
    feedback_category: str,
    corrected_response: str = "",
    clinical_comment: str = "",
    request_id: str,
) -> uuid.UUID:
    if decision not in DECISIONS:
        raise DomainError("unknown review decision", code="invalid_decision")
    if feedback_category not in FEEDBACK_CATEGORIES:
        raise DomainError("unknown feedback category", code="invalid_category")
    clean_scores = _validate_scores(scores)

    message, patient_id = await _assistant_message(session, message_id)
    await require_active_relationship(session, clinician_id=reviewer_id, patient_id=patient_id)

    corrected = corrected_response.strip()
    if decision == "EDIT" and not corrected:
        raise DomainError("an EDIT review must include a corrected response", code="correction_required")
    if decision != "EDIT":
        corrected = ""

    review_id = uuid.uuid4()
    session.add(
        ClinicianResponseReview(
            id=review_id,
            organization_id=organization_id,
            message_id=message_id,
            reviewer_id=reviewer_id,
            decision=decision,
            corrected_response_enc=encrypt(corrected) if corrected else None,
            scores_json=clean_scores,
            feedback_category=feedback_category,
            clinical_comment_enc=encrypt(clinical_comment.strip()[:4000]) if clinical_comment.strip() else None,
            model_version=message.responder_version,
            policy_version=None,
        )
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("you have already reviewed this response", code="already_reviewed") from exc

    await audit.record(
        session, request_id=request_id, action="ai_review.submit", resource_type="clinician_response_review",
        resource_id=str(review_id), organization_id=organization_id, actor_id=reviewer_id, outcome="SUCCESS",
        metadata={"decision": decision, "feedback_category": feedback_category, "model_version": message.responder_version},
    )
    if decision == "FLAG_SAFETY":
        await audit.record(
            session, request_id=request_id, action="ai_review.safety_flag", resource_type="clinician_response_review",
            resource_id=str(review_id), organization_id=organization_id, actor_id=reviewer_id, outcome="SUCCESS",
            metadata={"model_version": message.responder_version},
        )
        LOGGER.warning("ai_review safety flag review=%s model=%s", review_id, message.responder_version)
    return review_id


async def list_reviewable(
    session: AsyncSession, *, reviewer_id: uuid.UUID, patient_id: uuid.UUID
) -> list[dict]:
    """Réponses de l'assistant pour un patient suivi, avec le message patient qui
    les a déclenchées et l'indication de revue déjà faite (par n'importe qui)."""
    await require_active_relationship(session, clinician_id=reviewer_id, patient_id=patient_id)

    rows = (
        await session.execute(
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.patient_id == patient_id)
            .order_by(Conversation.id, Message.sequence_no)
        )
    ).scalars().all()

    reviewed = set(
        (
            await session.execute(select(ClinicianResponseReview.message_id).distinct())
        ).scalars().all()
    )
    mine = set(
        (
            await session.execute(
                select(ClinicianResponseReview.message_id).where(
                    ClinicianResponseReview.reviewer_id == reviewer_id
                )
            )
        ).scalars().all()
    )

    by_convo: dict[uuid.UUID, list[Message]] = {}
    for m in rows:
        by_convo.setdefault(m.conversation_id, []).append(m)

    out: list[dict] = []
    for messages in by_convo.values():
        for idx, m in enumerate(messages):
            if m.author_type != "ASSISTANT":
                continue
            prompt = messages[idx - 1] if idx > 0 and messages[idx - 1].author_type == "PATIENT" else None
            out.append(
                {
                    "message_id": str(m.id),
                    "conversation_id": str(m.conversation_id),
                    "assistant_response": decrypt(m.content_enc) or "",
                    "patient_message": (decrypt(prompt.content_enc) or "") if prompt is not None else None,
                    "generation_path": m.generation_path,
                    "model_version": m.responder_version,
                    "created_at": m.created_at.isoformat(),
                    "reviewed": m.id in reviewed,
                    "reviewed_by_me": m.id in mine,
                }
            )
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out


def _review_dict(review: ClinicianResponseReview) -> dict:
    return {
        "id": str(review.id),
        "decision": review.decision,
        "scores": review.scores_json,
        "feedback_category": review.feedback_category,
        "corrected_response": decrypt(review.corrected_response_enc) if review.corrected_response_enc else None,
        "clinical_comment": decrypt(review.clinical_comment_enc) if review.clinical_comment_enc else None,
        "model_version": review.model_version,
        "created_at": review.created_at.isoformat(),
    }


async def reviews_for_message(
    session: AsyncSession, *, reviewer_id: uuid.UUID, message_id: uuid.UUID
) -> list[dict]:
    _message, patient_id = await _assistant_message(session, message_id)
    await require_active_relationship(session, clinician_id=reviewer_id, patient_id=patient_id)
    rows = (
        await session.execute(
            select(ClinicianResponseReview)
            .where(ClinicianResponseReview.message_id == message_id)
            .order_by(ClinicianResponseReview.created_at.desc())
        )
    ).scalars().all()
    return [_review_dict(r) for r in rows]


async def model_quality_report(
    session: AsyncSession, *, model_version: str | None = None, since: dt.datetime | None = None
) -> dict:
    """Agrégat **par version de modèle** — jamais par relecteur. Alimente le
    tableau de bord qualité IA (perf de l'IA, pas du clinicien)."""
    filters = []
    if model_version is not None:
        filters.append(ClinicianResponseReview.model_version == model_version)
    if since is not None:
        filters.append(ClinicianResponseReview.created_at >= since)

    reviews = (
        await session.execute(select(ClinicianResponseReview).where(*filters))
    ).scalars().all()

    by_decision: dict[str, int] = dict.fromkeys(DECISIONS, 0)
    by_category: dict[str, int] = dict.fromkeys(FEEDBACK_CATEGORIES, 0)
    score_totals: dict[str, int] = dict.fromkeys(SCORE_DIMENSIONS, 0)
    for r in reviews:
        by_decision[r.decision] = by_decision.get(r.decision, 0) + 1
        by_category[r.feedback_category] = by_category.get(r.feedback_category, 0) + 1
        for dim in SCORE_DIMENSIONS:
            score_totals[dim] += int(r.scores_json.get(dim, 0))

    n = len(reviews)
    mean_scores = {dim: round(score_totals[dim] / n, 2) if n else None for dim in SCORE_DIMENSIONS}
    return {
        "model_version": model_version,
        "review_count": n,
        "by_decision": by_decision,
        "by_feedback_category": by_category,
        "mean_scores": mean_scores,
        "approval_rate": round(by_decision["APPROVE"] / n, 2) if n else None,
    }


async def list_safety_flags(
    session: AsyncSession, *, since: dt.datetime | None = None
) -> list[dict]:
    """Revues `FLAG_SAFETY` — signal pour l'équipe sécurité / politique. Ne
    déclenche jamais de changement automatique de politique de crise."""
    stmt = (
        select(ClinicianResponseReview)
        .where(ClinicianResponseReview.decision == "FLAG_SAFETY")
        .order_by(ClinicianResponseReview.created_at.desc())
    )
    if since is not None:
        stmt = stmt.where(ClinicianResponseReview.created_at >= since)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "message_id": str(r.message_id),
            "model_version": r.model_version,
            "feedback_category": r.feedback_category,
            "clinical_comment": decrypt(r.clinical_comment_enc) if r.clinical_comment_enc else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
