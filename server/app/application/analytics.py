"""Phase 15 — analytics produit, gouverné séparément du clinique (master
prompt §15). Deux règles structurelles, vérifiables par lecture du code :

1. Ce module ne lit ni n'écrit jamais dans les tables cliniques
   (`phq9_assessments`, `alerts`, `memories`, …) — uniquement `analytics_events`.
2. Chaque ligne porte un **pseudonyme rotatif** (HMAC de l'identifiant
   utilisateur, salé par semaine ISO), jamais l'UUID utilisateur en clair —
   impossible à re-joindre directement à un dossier patient depuis cette table.

Les événements `PRODUCT` (usage de l'app) exigent un consentement `ANALYTICS`
actif au moment de l'écriture ; les événements `AI_QUALITY` (comportement du
modèle, agrégés — jamais par patient nommé) n'en dépendent pas, à l'image du
rapport qualité IA déjà non-punitif de la Phase 14.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import consent
from app.core.config import get_settings
from app.infrastructure.models import AnalyticsEvent

_CATEGORIES = ("PRODUCT", "AI_QUALITY")


def _pseudonym(user_id: uuid.UUID) -> str:
    """HMAC(clé app, semaine ISO + user_id) — stable pendant 7 jours (permet un
    comptage d'utilisateurs actifs uniques par jour/semaine), non réversible
    sans la clé, et changé la semaine suivante."""
    settings = get_settings()
    week = dt.datetime.now(dt.UTC).strftime("%G-W%V")
    key = settings.jwt_signing_key.encode("utf-8")
    message = f"pi-analytics-pseudonym-v1:{week}:{user_id}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()[:32]


async def record_event(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    category: str,
    event_type: str,
    properties: dict | None = None,
) -> None:
    if category not in _CATEGORIES:
        raise ValueError(f"unknown analytics category: {category}")
    if category == "PRODUCT" and not await consent.has_active_consent(session, user_id, "ANALYTICS"):
        return
    session.add(
        AnalyticsEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            pseudonym=_pseudonym(user_id),
            category=category,
            event_type=event_type,
            properties=properties or {},
        )
    )
    await session.flush()


async def overview(session: AsyncSession, *, organization_id: uuid.UUID, days: int = 14) -> dict:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    day = func.date_trunc("day", AnalyticsEvent.occurred_at)

    by_type_rows = (
        await session.execute(
            select(AnalyticsEvent.event_type, func.count())
            .where(AnalyticsEvent.organization_id == organization_id, AnalyticsEvent.occurred_at >= since)
            .group_by(AnalyticsEvent.event_type)
        )
    ).all()

    dau_rows = (
        await session.execute(
            select(day.label("day"), func.count(func.distinct(AnalyticsEvent.pseudonym)))
            .where(
                AnalyticsEvent.organization_id == organization_id,
                AnalyticsEvent.category == "PRODUCT",
                AnalyticsEvent.occurred_at >= since,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    messages_per_day_rows = (
        await session.execute(
            select(day.label("day"), func.count())
            .where(
                AnalyticsEvent.organization_id == organization_id,
                AnalyticsEvent.event_type == "message_sent",
                AnalyticsEvent.occurred_at >= since,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    path_expr = AnalyticsEvent.properties["generation_path"].astext
    level_expr = AnalyticsEvent.properties["decision_level"].astext
    ai_quality_rows = (
        await session.execute(
            select(path_expr, level_expr, func.count())
            .where(
                AnalyticsEvent.organization_id == organization_id,
                AnalyticsEvent.category == "AI_QUALITY",
                AnalyticsEvent.occurred_at >= since,
            )
            .group_by(path_expr, level_expr)
        )
    ).all()

    return {
        "since": since.isoformat(),
        "totals_by_event_type": {event_type: count for event_type, count in by_type_rows},
        "daily_active_users": [{"date": d.date().isoformat(), "count": c} for d, c in dau_rows],
        "messages_per_day": [{"date": d.date().isoformat(), "count": c} for d, c in messages_per_day_rows],
        "ai_responses_by_path_and_level": [
            {"generation_path": path, "decision_level": level, "count": count}
            for path, level, count in ai_quality_rows
        ],
    }
