from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import AuditLog

# Clés interdites dans metadata_json : aucune donnée clinique, aucun secret
# (threat-model-v2, hérité de v1 TH-09).
_FORBIDDEN = {"content", "password", "token", "about_me", "answers", "mfa_secret", "api_key"}


async def record(
    session: AsyncSession,
    *,
    request_id: str,
    action: str,
    resource_type: str,
    outcome: str,
    organization_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    clean = {k: v for k, v in (metadata or {}).items() if k.lower() not in _FORBIDDEN}
    await session.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            request_id=request_id,
            correlation_id=correlation_id,
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            metadata_json=clean,
        )
    )
