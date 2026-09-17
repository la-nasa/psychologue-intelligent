"""Phase 17 — Model Registry (ADR-011). Réservé aux rôles pouvant approuver un
modèle (`model.approve` : PSYCHOLOGIST, CLINICAL_SUPERVISOR, ML_ENGINEER) ;
lecture seule ouverte en plus au SUPER_ADMIN (oversight plateforme, jamais de
mutation directe sans le rôle métier)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, RequestId
from app.application.rbac import require_permission
from app.core.db import tenant_session
from app.mlops import registry

router = APIRouter(prefix="/api/v1/mlops", tags=["mlops"])


class ModelRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)
    notes: str = Field(default="", max_length=4000)


class ModelPromoteRequest(BaseModel):
    target_stage: str = Field(min_length=1, max_length=16)


class ModelRollbackRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.get("/models")
async def list_models(principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        if not principal.has_role("SUPER_ADMIN"):
            await require_permission(session, principal, "model.approve")
        return {"items": await registry.list_versions(session, organization_id=principal.organization_id)}


@router.post("/models", status_code=status.HTTP_201_CREATED)
async def register_model(body: ModelRegisterRequest, principal: CurrentPrincipal, request_id: RequestId) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "model.approve")
        row = await registry.register_version(
            session, organization_id=principal.organization_id, name=body.name, version=body.version,
            notes=body.notes, actor_id=principal.user_id, request_id=request_id,
        )
    return {"id": str(row.id)}


@router.post("/models/{model_version_id}/promote")
async def promote_model(
    model_version_id: str, body: ModelPromoteRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "model.approve")
        row = await registry.promote(
            session, organization_id=principal.organization_id, model_version_id=uuid.UUID(model_version_id),
            target_stage=body.target_stage, actor_id=principal.user_id, request_id=request_id,
        )
    return registry.to_dict(row)


@router.post("/models/{model_version_id}/rollback")
async def rollback_model(
    model_version_id: str, body: ModelRollbackRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await require_permission(session, principal, "model.approve")
        row = await registry.rollback(
            session, organization_id=principal.organization_id, model_version_id=uuid.UUID(model_version_id),
            actor_id=principal.user_id, reason=body.reason, request_id=request_id,
        )
    return registry.to_dict(row)
