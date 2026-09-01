"""Canaux de notification par organisation (data-model-v2 §4, master prompt §33).

`resolve` renvoie les canaux **actifs** de l'organisation. Repli sur les canaux
nommés dans la politique de crise (`crisis-policy.json`) uniquement quand aucun
canal n'est configuré en base — un canal du repli est de type `log` (dev),
jamais un vrai destinataire deviné.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError
from app.infrastructure.models import NotificationChannel

_KINDS = ("email", "sms", "push", "log")


@dataclass(frozen=True)
class ResolvedChannel:
    name: str
    kind: str
    target: str


async def resolve(
    session: AsyncSession, *, organization_id: uuid.UUID, policy_channels: tuple[str, ...]
) -> tuple[ResolvedChannel, ...]:
    rows = (
        await session.execute(
            select(NotificationChannel).where(
                NotificationChannel.organization_id == organization_id,
                NotificationChannel.is_active.is_(True),
            )
        )
    ).scalars().all()
    if rows:
        return tuple(ResolvedChannel(r.name, r.kind, decrypt(r.target_enc) or "") for r in rows)
    # Repli politique : canaux de dev (log), jamais un destinataire réel deviné.
    return tuple(ResolvedChannel(name, "log", name) for name in policy_channels)


async def create_channel(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str,
    kind: str,
    target: str,
    request_id: str,
) -> uuid.UUID:
    if kind not in _KINDS:
        raise DomainError("unknown channel kind", code="unknown_kind")
    if not name.strip() or not target.strip():
        raise DomainError("channel name and target are required", code="invalid_channel")
    channel_id = uuid.uuid4()
    session.add(
        NotificationChannel(
            id=channel_id, organization_id=organization_id, name=name.strip()[:60],
            kind=kind, target_enc=encrypt(target.strip()) or "", is_active=True,
        )
    )
    await session.flush()  # rend la ligne interrogeable dans la même session (autoflush=False)
    await audit.record(
        session, request_id=request_id, action="notification_channel.create", resource_type="notification_channel",
        resource_id=str(channel_id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"kind": kind, "name": name},
    )
    return channel_id


async def list_channels(session: AsyncSession, organization_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(NotificationChannel)
            .where(NotificationChannel.organization_id == organization_id)
            .order_by(NotificationChannel.created_at)
        )
    ).scalars().all()
    # La cible n'est jamais renvoyée en clair dans une liste — seulement un indice.
    return [
        {"id": str(r.id), "name": r.name, "kind": r.kind, "is_active": r.is_active, "target_hint": _hint(decrypt(r.target_enc) or "")}
        for r in rows
    ]


def _hint(target: str) -> str:
    if "@" in target:
        user, _, domain = target.partition("@")
        return f"{user[:2]}***@{domain}"
    return target[:2] + "***" if len(target) > 2 else "***"
