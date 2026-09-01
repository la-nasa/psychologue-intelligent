from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import Phq9SubmitRequest, Phq9SubmitResponse, ReminderRequest
from app.application import assessment
from app.core.config import get_settings
from app.core.context import Principal
from app.core.db import tenant_session
from app.core.errors import RateLimitedError
from app.core.redis import rate_limit_allow

router = APIRouter(prefix="/api/v1/assessments", tags=["assessment"])


async def _rate_limit(principal: Principal) -> None:
    if not await rate_limit_allow(
        "phq9", str(principal.user_id), limit=get_settings().rate_limit_phq9_per_hour, window_seconds=3600
    ):
        raise RateLimitedError("too many assessments submitted")


@router.post("/phq9", response_model=Phq9SubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_phq9(
    body: Phq9SubmitRequest, request: Request, principal: CurrentPrincipal, request_id: RequestId
) -> Phq9SubmitResponse:
    await _rate_limit(principal)
    state = request.app.state
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        result = await assessment.submit_phq9(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            answers=body.answers, config=state.safety, notification_provider=state.notification_provider,
            request_id=request_id,
        )
    return Phq9SubmitResponse(**{k: v for k, v in result.items() if k != "alert_id"})


@router.get("/phq9")
async def phq9_history(principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await assessment.history(session, principal.user_id)}


@router.get("/phq9/trend")
async def phq9_trend(principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return await assessment.trend(session, principal.user_id)


@router.get("/phq9/{assessment_id}/answers")
async def phq9_answers(assessment_id: str, principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"answers": await assessment.answers_for(session, principal.user_id, uuid.UUID(assessment_id))}


@router.post("/reminders", status_code=status.HTTP_201_CREATED)
async def schedule_reminder(
    body: ReminderRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        reminder_id = await assessment.schedule_reminder(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            due_at=body.due_at, request_id=request_id,
        )
    return {"id": str(reminder_id)}


@router.get("/reminders")
async def list_reminders(principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await assessment.list_reminders(session, principal.user_id)}
