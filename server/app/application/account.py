"""Suppression de compte — porté de v1 (demande, pas suppression immédiate).

Une demande est enregistrée (`OPEN`) ; elle n'efface pas immédiatement les
traces d'audit légalement requises. Le traitement effectif suit la politique de
rétention validée (hors périmètre logiciel à ce stade — voir production-readiness).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.infrastructure.models import DeletionRequest


async def request_deletion(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, request_id: str
) -> str:
    existing = (
        await session.execute(
            select(DeletionRequest).where(DeletionRequest.user_id == user_id, DeletionRequest.status == "OPEN")
        )
    ).scalar_one_or_none()
    if existing is not None:
        return "OPEN"
    session.add(
        DeletionRequest(id=uuid.uuid4(), organization_id=organization_id, user_id=user_id, status="OPEN")
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="account.deletion_requested", resource_type="user",
        resource_id=str(user_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )
    return "OPEN"
