"""Clinician AI Review (master prompt §38-39).

Usage **non punitif** : voir `docs/governance/ai-review-non-punitive.md`. Aucun
endpoint n'agrège les revues par relecteur.
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import AiReviewRequest
from app.application import ai_review
from app.application.rbac import require_role
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1/clinician/ai-review", tags=["clinician", "ai-review"])

_REVIEWER_ROLES = ("PSYCHOLOGIST", "CLINICAL_SUPERVISOR")
_OVERSIGHT_ROLES = ("CLINICAL_SUPERVISOR", "SUPER_ADMIN")


def _parse_since(since: str | None) -> dt.datetime | None:
    if not since:
        return None
    try:
        return dt.datetime.fromisoformat(since)
    except ValueError:
        return None


@router.get("/patients/{patient_id}/messages")
async def list_reviewable(patient_id: str, principal: CurrentPrincipal) -> dict:
    require_role(principal, *_REVIEWER_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {
            "items": await ai_review.list_reviewable(
                session, reviewer_id=principal.user_id, patient_id=uuid.UUID(patient_id)
            )
        }


@router.post("/messages/{message_id}/review", status_code=status.HTTP_201_CREATED)
async def submit_review(
    message_id: str, body: AiReviewRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    require_role(principal, *_REVIEWER_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        review_id = await ai_review.submit_review(
            session,
            organization_id=principal.organization_id,
            reviewer_id=principal.user_id,
            message_id=uuid.UUID(message_id),
            decision=body.decision,
            scores=body.scores,
            feedback_category=body.feedback_category,
            corrected_response=body.corrected_response,
            clinical_comment=body.clinical_comment,
            request_id=request_id,
        )
    return {"id": str(review_id)}


@router.get("/messages/{message_id}/reviews")
async def reviews_for_message(message_id: str, principal: CurrentPrincipal) -> dict:
    require_role(principal, *_REVIEWER_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {
            "items": await ai_review.reviews_for_message(
                session, reviewer_id=principal.user_id, message_id=uuid.UUID(message_id)
            )
        }


@router.get("/quality-report")
async def quality_report(
    principal: CurrentPrincipal, model_version: str | None = None, since: str | None = None
) -> dict:
    require_role(principal, *_OVERSIGHT_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return await ai_review.model_quality_report(
            session, model_version=model_version, since=_parse_since(since)
        )


@router.get("/safety-flags")
async def safety_flags(principal: CurrentPrincipal, since: str | None = None) -> dict:
    require_role(principal, *_OVERSIGHT_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await ai_review.list_safety_flags(session, since=_parse_since(since))}
