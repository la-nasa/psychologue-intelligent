"""Consentement versionné et révocable (data-model-v2 §3, ADR-007).

Chaque finalité (`CARE`, `LEARNING`, `AI_EXTERNAL`, `VOICE`, `ANALYTICS`,
`RESEARCH`) est consentie séparément, contre une version de texte donnée, et
peut être révoquée. `has_active_consent` est le point de contrôle utilisé par
le moteur de conversation (Phase 4) et le pipeline d'apprentissage (Phase 16).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.errors import DomainError
from app.infrastructure.models import Consent, ConsentVersion

VALID_PURPOSES = ("CARE", "LEARNING", "AI_EXTERNAL", "VOICE", "ANALYTICS", "RESEARCH")


def _validate(purpose: str) -> None:
    if purpose not in VALID_PURPOSES:
        raise DomainError("unknown consent purpose", code="unknown_purpose")


async def current_version(session: AsyncSession, purpose: str) -> str:
    row = await session.execute(
        select(ConsentVersion.version).where(ConsentVersion.purpose == purpose).order_by(ConsentVersion.published_at.desc())
    )
    version = row.scalars().first()
    if version is None:
        raise DomainError("no published consent text for this purpose", code="no_consent_version")
    return version


async def grant(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, purpose: str, request_id: str
) -> None:
    _validate(purpose)
    version = await current_version(session, purpose)
    existing = (
        await session.execute(
            select(Consent).where(
                Consent.user_id == user_id, Consent.purpose == purpose, Consent.version == version
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.revoked_at is not None:
            existing.revoked_at = None  # re-consentement à la même version
            existing.granted_at = dt.datetime.now(dt.UTC)
    else:
        session.add(
            Consent(
                id=uuid.uuid4(), organization_id=organization_id, user_id=user_id,
                purpose=purpose, version=version, evidence_ref=request_id,
            )
        )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="consent.grant", resource_type="consent",
        resource_id=f"{purpose}:{version}", organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
        metadata={"purpose": purpose, "version": version},
    )


async def revoke(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, purpose: str, request_id: str
) -> None:
    _validate(purpose)
    rows = (
        await session.execute(
            select(Consent).where(
                Consent.user_id == user_id, Consent.purpose == purpose, Consent.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    now = dt.datetime.now(dt.UTC)
    for consent in rows:
        consent.revoked_at = now
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="consent.revoke", resource_type="consent",
        resource_id=purpose, organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
        metadata={"purpose": purpose, "revoked_count": len(rows)},
    )
    # Cascade sur la mémoire (threat-model-v2 TV-05) : une mémoire dont le
    # consentement est retiré ne doit plus jamais être réinjectée. Import différé
    # pour éviter un cycle consent <-> memory.
    from app.application import memory

    await memory.forget_for_consent(
        session, organization_id=organization_id, user_id=user_id, purpose=purpose, request_id=request_id
    )


async def has_active_consent(session: AsyncSession, user_id: uuid.UUID, purpose: str) -> bool:
    row = await session.execute(
        select(Consent.id).where(
            Consent.user_id == user_id, Consent.purpose == purpose, Consent.revoked_at.is_(None)
        ).limit(1)
    )
    return row.scalar_one_or_none() is not None


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(Consent).where(Consent.user_id == user_id).order_by(Consent.granted_at.desc())
        )
    ).scalars().all()
    return [
        {
            "purpose": c.purpose,
            "version": c.version,
            "granted_at": c.granted_at.isoformat(),
            "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            "active": c.revoked_at is None,
        }
        for c in rows
    ]
