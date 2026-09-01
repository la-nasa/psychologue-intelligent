"""MemoryService (overview-v2 §6, data-model-v2 §5).

Quatre niveaux : WORKING (session courante — porté par le contexte de tour),
EPISODIC (événements racontés par le patient — ses messages), SEMANTIC et
LONGITUDINAL (dérivés par des jobs, Phase 15/16).

INVARIANTS (threat-model-v2) :
- TV-04 : une mémoire `MODEL_INFERRED` porte une confiance explicite et n'est
  jamais traitée comme un fait ; un patient ne peut pas créer de mémoire
  `CLINICIAN_VALIDATED`.
- TV-05 : une mémoire `REVOKED` / `EXPIRED` / `UNCERTAIN` n'est jamais renvoyée
  par `retrieve` (filtre `status = 'ACTIVE'` + fenêtre d'expiration).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.embedding import HashingEmbeddingModel
from app.application import audit
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError
from app.infrastructure.models import Memory

_EMBED = HashingEmbeddingModel()
_RETRIEVABLE = ("ACTIVE",)  # CLINICIAN_VALIDATED deviendra récupérable en Phase 14


async def remember(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    type: str = "EPISODIC",
    provenance: str = "USER_DECLARED",
    confidence: float | None = None,
    consent_scope: str = "CARE",
    sensitivity: str = "normal",
    source_conversation_id: uuid.UUID | None = None,
    source_message_id: uuid.UUID | None = None,
    expires_at: dt.datetime | None = None,
    request_id: str,
) -> uuid.UUID:
    content = (content or "").strip()
    if not content:
        raise DomainError("cannot store an empty memory", code="empty_memory")
    if provenance == "MODEL_INFERRED" and confidence is None:
        raise DomainError("a model-inferred memory requires an explicit confidence", code="confidence_required")
    if provenance == "CLINICIAN_VALIDATED":
        raise DomainError("clinician validation is not a self-service provenance", code="forbidden_provenance")
    resolved_confidence = 1.0 if confidence is None else max(0.0, min(1.0, confidence))

    memory_id = uuid.uuid4()
    session.add(
        Memory(
            id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            type=type,
            content_enc=encrypt(content) or "",
            embedding=_EMBED.embed(content),
            provenance=provenance,
            confidence=resolved_confidence,
            sensitivity=sensitivity,
            consent_scope=consent_scope,
            status="ACTIVE",
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            expires_at=expires_at,
        )
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="memory.remember", resource_type="memory",
        resource_id=str(memory_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
        metadata={"type": type, "provenance": provenance},
    )
    return memory_id


async def retrieve(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_text: str,
    limit: int = 3,
    types: tuple[str, ...] | None = None,
) -> list[dict]:
    query_vec = _EMBED.embed(query_text)
    now = dt.datetime.now(dt.UTC)
    stmt = (
        select(Memory, Memory.embedding.cosine_distance(query_vec).label("distance"))
        .where(
            Memory.user_id == user_id,
            Memory.status.in_(_RETRIEVABLE),
            (Memory.expires_at.is_(None)) | (Memory.expires_at > now),
        )
        .order_by("distance")
        .limit(limit * 3)  # sur-échantillonne, puis re-classe par pertinence + récence + confiance
    )
    if types:
        stmt = stmt.where(Memory.type.in_(types))
    rows = (await session.execute(stmt)).all()

    scored: list[tuple[float, Memory]] = []
    for memory, distance in rows:
        relevance = 1.0 - float(distance)          # cosinus : 1 = identique
        age_days = max((now - memory.created_at).days, 0)
        recency = 1.0 / (1.0 + age_days / 30.0)    # décroît sur ~1 mois
        score = 0.7 * relevance + 0.15 * recency + 0.15 * memory.confidence
        scored.append((score, memory))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [
        {
            "id": str(memory.id),
            "type": memory.type,
            "provenance": memory.provenance,
            "confidence": memory.confidence,
            "content": decrypt(memory.content_enc) or "",
            "created_at": memory.created_at.isoformat(),
        }
        for _, memory in scored[:limit]
    ]


async def forget_for_consent(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    purpose: str,
    request_id: str,
) -> int:
    """Révocation de consentement -> cascade sur la mémoire (TV-05).
    `CARE` révoqué : toute la mémoire de conversation du patient est révoquée
    (CARE est le socle). Un périmètre plus fin ne révoque que les mémoires
    portant ce `consent_scope`."""
    stmt = update(Memory).where(Memory.user_id == user_id, Memory.status != "REVOKED")
    if purpose != "CARE":
        stmt = stmt.where(Memory.consent_scope == purpose)
    stmt = stmt.values(status="REVOKED", updated_at=dt.datetime.now(dt.UTC))
    result = await session.execute(stmt)
    revoked = result.rowcount or 0  # type: ignore[attr-defined]
    if revoked:
        await audit.record(
            session, request_id=request_id, action="memory.revoked", resource_type="memory",
            resource_id=purpose, organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
            metadata={"purpose": purpose, "count": revoked},
        )
    return revoked


async def expire_due(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    moment = now or dt.datetime.now(dt.UTC)
    result = await session.execute(
        update(Memory)
        .where(Memory.status == "ACTIVE", Memory.expires_at.is_not(None), Memory.expires_at <= moment)
        .values(status="EXPIRED", updated_at=moment)
    )
    return result.rowcount or 0  # type: ignore[attr-defined]
