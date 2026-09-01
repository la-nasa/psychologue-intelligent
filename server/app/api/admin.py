from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import ChannelCreateRequest, ChannelItem, RelationshipCreateRequest, RelationshipItem
from app.application import channels, relationships
from app.application.rbac import require_role
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_ADMIN_ROLES = ("ADMIN", "SUPER_ADMIN")


@router.get("/notification-channels", response_model=dict[str, list[ChannelItem]])
async def list_channels(principal: CurrentPrincipal) -> dict:
    require_role(principal, *_ADMIN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await channels.list_channels(session, principal.organization_id)}


@router.post("/notification-channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreateRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    require_role(principal, *_ADMIN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        channel_id = await channels.create_channel(
            session, organization_id=principal.organization_id, actor_id=principal.user_id,
            name=body.name, kind=body.kind, target=body.target, request_id=request_id,
        )
    return {"id": str(channel_id)}


# --- Phase 12 : relations patient-clinicien (`admin.relationships.manage`) ---


@router.get("/relationships", response_model=dict[str, list[RelationshipItem]])
async def list_relationships(principal: CurrentPrincipal, active_only: bool = False) -> dict:
    require_role(principal, *_ADMIN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {
            "items": await relationships.list_relationships(
                session, organization_id=principal.organization_id, active_only=active_only
            )
        }


@router.post("/relationships", status_code=status.HTTP_201_CREATED)
async def create_relationship(
    body: RelationshipCreateRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    require_role(principal, *_ADMIN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        relationship_id = await relationships.create_relationship(
            session, organization_id=principal.organization_id, actor_id=principal.user_id,
            patient_id=uuid.UUID(body.patient_id), clinician_id=uuid.UUID(body.clinician_id),
            request_id=request_id,
        )
    return {"id": str(relationship_id)}


@router.delete("/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_relationship(
    relationship_id: str, principal: CurrentPrincipal, request_id: RequestId
) -> Response:
    require_role(principal, *_ADMIN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await relationships.end_relationship(
            session, organization_id=principal.organization_id, actor_id=principal.user_id,
            relationship_id=uuid.UUID(relationship_id), request_id=request_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
