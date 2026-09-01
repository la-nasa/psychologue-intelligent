"""Profil utilisateur + préférences de communication (Phase 3).

`about_me` est un texte librement écrit par le patient, chiffré au repos
(threat-model-v2 TV-03 : il est injecté plus tard dans le message système du
LLM, jamais comme instruction). L'onboarding n'est marqué qu'une seule fois.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.crypto import decrypt, encrypt
from app.infrastructure.models import CommunicationPreference, Profile

_LANGUAGES = ("fr", "en")


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> dict:
    row = (await session.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    if row is None:
        return {"display_name": "", "about_me": "", "language": "fr", "onboarding_completed_at": None}
    return {
        "display_name": row.display_name,
        "about_me": decrypt(row.about_me_enc) or "",
        "language": row.language,
        "onboarding_completed_at": row.onboarding_completed_at.isoformat() if row.onboarding_completed_at else None,
    }


async def save_profile(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    display_name: str,
    about_me: str,
    language: str,
    request_id: str,
) -> None:
    if language not in _LANGUAGES:
        language = "fr"
    now = dt.datetime.now(dt.UTC)
    row = (await session.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    first_save = row is None or row.onboarding_completed_at is None
    if row is None:
        row = Profile(user_id=user_id, organization_id=organization_id)
        session.add(row)
    row.display_name = display_name.strip()[:100]
    row.about_me_enc = encrypt(about_me.strip()[:2000] or None)
    row.language = language
    row.updated_at = now
    if first_save and row.onboarding_completed_at is None:
        row.onboarding_completed_at = now
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="profile.save", resource_type="profile",
        resource_id=str(user_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> dict:
    row = (
        await session.execute(select(CommunicationPreference).where(CommunicationPreference.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        return {"tone": "warm", "response_length": "medium", "question_frequency": "medium", "directiveness": "balanced"}
    return {
        "tone": row.tone,
        "response_length": row.response_length,
        "question_frequency": row.question_frequency,
        "directiveness": row.directiveness,
    }


async def save_preferences(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    tone: str,
    response_length: str,
    question_frequency: str,
    directiveness: str,
    request_id: str,
) -> None:
    row = (
        await session.execute(select(CommunicationPreference).where(CommunicationPreference.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        row = CommunicationPreference(user_id=user_id, organization_id=organization_id)
        session.add(row)
    row.tone = tone
    row.response_length = response_length
    row.question_frequency = question_frequency
    row.directiveness = directiveness
    row.updated_at = dt.datetime.now(dt.UTC)
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="preferences.save", resource_type="communication_preference",
        resource_id=str(user_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )
