from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import ChannelCreateRequest, ChannelItem
from app.application import channels
from app.application.rbac import require_role
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/notification-channels", response_model=dict[str, list[ChannelItem]])
async def list_channels(principal: CurrentPrincipal) -> dict:
    require_role(principal, "ADMIN", "SUPER_ADMIN")
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await channels.list_channels(session, principal.organization_id)}


@router.post("/notification-channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreateRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    require_role(principal, "ADMIN", "SUPER_ADMIN")
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        channel_id = await channels.create_channel(
            session, organization_id=principal.organization_id, actor_id=principal.user_id,
            name=body.name, kind=body.kind, target=body.target, request_id=request_id,
        )
    return {"id": str(channel_id)}
