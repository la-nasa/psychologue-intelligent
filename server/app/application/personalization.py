"""PersonalizationEngine (master prompt §20-21, §27, overview-v2 §5).

Résout un **style d'interaction effectif** à partir des préférences déclarées
(Phase 3), des objectifs actifs (§56) et de la langue du profil. Ce style est
tissé dans le message système par `ai/prompt.build_messages`, jamais dans le
chemin de sécurité.

INVARIANT (master prompt §85, overview-v2 §15) : la personnalisation ne peut
faire varier que la réponse GREEN. Les réponses ORANGE/RED viennent de gabarits
fixes, identiques quel que soit le profil — vérifié par test
(`test_personalization.py::test_safety_reply_is_identical_regardless_of_profile`).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.application import goals as goals_mod
from app.application import profile as profile_mod

LOGGER = logging.getLogger("pi.personalization")

_TONES = ("warm", "neutral", "direct")
_LENGTHS = ("short", "medium", "detailed")
_FREQ = ("low", "medium", "high")
_DIRECTIVE = ("reflective", "balanced", "directive")


@dataclass(frozen=True)
class InteractionStyle:
    tone: str = "warm"
    response_length: str = "medium"
    question_frequency: str = "medium"
    directiveness: str = "balanced"
    language: str = "fr"
    active_goals: tuple[str, ...] = ()

    def as_context(self) -> dict:
        data = asdict(self)
        data["active_goals"] = list(self.active_goals)
        return data


def _coerce(value: str | None, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


async def resolve_style(session: AsyncSession, user_id: uuid.UUID) -> InteractionStyle:
    prefs: dict = {}
    profile_row: dict = {}
    active_goals: list[str] = []
    try:
        prefs = await profile_mod.get_preferences(session, user_id)
        profile_row = await profile_mod.get_profile(session, user_id)
        active_goals = await goals_mod.list_active_titles(session, user_id)
    except Exception:  # best-effort : jamais bloquant (overview-v2 §5)
        LOGGER.exception("style resolution degraded; using defaults")

    return InteractionStyle(
        tone=_coerce(prefs.get("tone"), _TONES, "warm"),
        response_length=_coerce(prefs.get("response_length"), _LENGTHS, "medium"),
        question_frequency=_coerce(prefs.get("question_frequency"), _FREQ, "medium"),
        directiveness=_coerce(prefs.get("directiveness"), _DIRECTIVE, "balanced"),
        language=_coerce(profile_row.get("language"), ("fr", "en"), "fr"),
        active_goals=tuple(active_goals[:5]),
    )
