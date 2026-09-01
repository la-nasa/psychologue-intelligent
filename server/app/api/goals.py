from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import GoalCreateRequest, GoalItem, GoalProgressRequest
from app.application import goals
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1", tags=["goals"])


@router.get("/goals", response_model=dict[str, list[GoalItem]])
async def list_goals(principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await goals.list_goals(session, principal.user_id)}


@router.post("/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(body: GoalCreateRequest, principal: CurrentPrincipal, request_id: RequestId) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        goal_id = await goals.create_goal(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            title=body.title, description=body.description, request_id=request_id,
        )
    return {"id": str(goal_id)}


@router.post("/goals/{goal_id}/progress", status_code=status.HTTP_204_NO_CONTENT)
async def record_progress(
    goal_id: str, body: GoalProgressRequest, principal: CurrentPrincipal, request_id: RequestId
) -> Response:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await goals.record_progress(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            goal_id=uuid.UUID(goal_id), value=body.value, note=body.note, request_id=request_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
