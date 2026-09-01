"""Endpoints « plateforme clinicien » (master prompt §33).

RBAC deny-by-default : réservés aux rôles `PSYCHOLOGIST` / `CLINICAL_SUPERVISOR`
(`require_role`). Chaque accès nominatif à un dossier patient repasse par la
relation `ACTIVE` patient-clinicien.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import AlertActionRequest
from app.application import alerts, clinician
from app.application.rbac import require_role
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1/clinician", tags=["clinician"])

_CLINICIAN_ROLES = ("PSYCHOLOGIST", "CLINICAL_SUPERVISOR")


@router.get("/overview")
async def get_overview(principal: CurrentPrincipal) -> dict:
    require_role(principal, *_CLINICIAN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return await clinician.overview(session, clinician_id=principal.user_id)


@router.get("/patients")
async def get_patients(principal: CurrentPrincipal) -> dict:
    require_role(principal, *_CLINICIAN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await clinician.list_patients(session, clinician_id=principal.user_id)}


@router.get("/patients/{patient_id}/timeline")
async def get_patient_timeline(patient_id: str, principal: CurrentPrincipal) -> dict:
    require_role(principal, *_CLINICIAN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return await clinician.patient_timeline(
            session, clinician_id=principal.user_id, patient_id=uuid.UUID(patient_id)
        )


@router.get("/alerts")
async def get_alerts(
    principal: CurrentPrincipal, level: str | None = None, status: str | None = None
) -> dict:
    require_role(principal, *_CLINICIAN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {
            "items": await clinician.list_alerts(
                session, clinician_id=principal.user_id, level=level, status=status
            )
        }


@router.post("/alerts/{alert_id}/actions")
async def act_on_alert(
    alert_id: str, body: AlertActionRequest, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    require_role(principal, *_CLINICIAN_ROLES)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        updated = await alerts.act_on_alert(
            session,
            organization_id=principal.organization_id,
            clinician_id=principal.user_id,
            alert_id=uuid.UUID(alert_id),
            target=body.target,
            justification=body.justification,
            request_id=request_id,
        )
        return clinician.alert_row(updated)
