"""Objectifs de travail — master prompt §56-57.

Un objectif n'est **jamais** créé automatiquement : seule la personne le pose.
`list_active_titles` alimente le contexte de personnalisation (Phase 6).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError, NotFoundError
from app.infrastructure.models import Goal, GoalProgress

_MAX_ACTIVE_GOALS = 5


async def create_goal(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, title: str, description: str, request_id: str
) -> uuid.UUID:
    title = (title or "").strip()
    if not (0 < len(title) <= 160):
        raise DomainError("a goal needs a short title", code="invalid_goal")
    active = (
        await session.execute(
            select(Goal).where(Goal.user_id == user_id, Goal.status == "ACTIVE")
        )
    ).scalars().all()
    if len(active) >= _MAX_ACTIVE_GOALS:
        raise DomainError("too many active goals; pause or drop one first", code="too_many_goals")

    goal_id = uuid.uuid4()
    session.add(
        Goal(
            id=goal_id, organization_id=organization_id, user_id=user_id,
            title=title, description_enc=encrypt(description.strip()[:2000] or None), status="ACTIVE",
        )
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="goal.create", resource_type="goal",
        resource_id=str(goal_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )
    return goal_id


async def list_goals(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at.desc()))
    ).scalars().all()
    out = []
    for goal in rows:
        latest = (
            await session.execute(
                select(GoalProgress.value)
                .where(GoalProgress.goal_id == goal.id)
                .order_by(GoalProgress.recorded_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append(
            {
                "id": str(goal.id),
                "title": goal.title,
                "description": decrypt(goal.description_enc) or "",
                "status": goal.status,
                "progress": latest or 0,
            }
        )
    return out


async def list_active_titles(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = (
        await session.execute(
            select(Goal.title).where(Goal.user_id == user_id, Goal.status == "ACTIVE").order_by(Goal.created_at)
        )
    ).scalars().all()
    return list(rows)


async def record_progress(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    value: int,
    note: str,
    request_id: str,
) -> None:
    goal = (await session.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
    if goal is None or goal.user_id != user_id:
        raise NotFoundError("no such goal for this user")
    if not (0 <= value <= 100):
        raise DomainError("progress is a percentage 0-100", code="invalid_progress")
    session.add(
        GoalProgress(
            id=uuid.uuid4(), organization_id=organization_id, goal_id=goal_id,
            value=value, note_enc=encrypt(note.strip()[:1000] or None),
        )
    )
    if value >= 100 and goal.status == "ACTIVE":
        goal.status = "ACHIEVED"
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="goal.progress", resource_type="goal",
        resource_id=str(goal_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
        metadata={"value": value},
    )
