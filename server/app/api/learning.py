"""Phase 16 — file de revue de l'apprentissage continu. Réservé aux rôles
pouvant réviser (`learning.review` : PSYCHOLOGIST, CLINICAL_SUPERVISOR,
ML_ENGINEER) ; promotion/rollback réservés à `model.approve`."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, RequestId
from app.application import learning
from app.application.rbac import require_permission
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


class RollbackRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.get("/samples")
async def list_samples(principal: CurrentPrincipal, status: str | None = None) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "learning.review")
        return {
            "items": await learning.list_samples(session, organization_id=principal.organization_id, status=status)
        }


@router.post("/samples/{sample_id}/review", status_code=status.HTTP_200_OK)
async def review_sample(
    sample_id: str, body: ReviewRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "learning.review")
        row = await learning.review(
            session, organization_id=principal.organization_id, sample_id=uuid.UUID(sample_id),
            reviewer_id=principal.user_id, reviewer_roles=principal.roles, decision=body.decision,
            request_id=request_id,
        )
    return learning.to_dict(row)


@router.post("/samples/{sample_id}/promote")
async def promote_sample(sample_id: str, principal: CurrentPrincipal, request_id: RequestId) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "model.approve")
        row = await learning.promote(
            session, organization_id=principal.organization_id, sample_id=uuid.UUID(sample_id),
            actor_id=principal.user_id, request_id=request_id,
        )
    return learning.to_dict(row)


@router.post("/samples/{sample_id}/rollback")
async def rollback_sample(
    sample_id: str, body: RollbackRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "model.approve")
        row = await learning.rollback(
            session, organization_id=principal.organization_id, sample_id=uuid.UUID(sample_id),
            actor_id=principal.user_id, reason=body.reason, request_id=request_id,
        )
    return learning.to_dict(row)
