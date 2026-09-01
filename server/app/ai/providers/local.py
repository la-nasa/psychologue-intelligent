"""Répondeur de soutien local, non génératif, streamé — Phase 4.

Concret derrière `StreamingLLMProvider`. Compose une réponse
ACKNOWLEDGE → (REFLECT) → une question, à partir de gabarits + du contexte.
Ce n'est PAS une IA conversationnelle et ne doit jamais être présenté comme
telle : c'est le comportement par défaut du FAST path et le repli du DEEP path,
en attendant un adaptateur `local` réellement génératif (llama.cpp, ADR-005/007)
ou l'adaptateur `external`. Toujours GREEN uniquement (voir `compose_reply`).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.ai.prompt import ChatMessage

_OPENERS = (
    "Merci d'avoir partagé cela.",
    "J'entends que ce moment compte pour vous.",
    "Merci pour ce message.",
)
_QUESTIONS = (
    "Qu'est-ce qui pèse le plus pour vous en ce moment ?",
    "Comment vous sentez-vous par rapport à cela aujourd'hui ?",
    "Y a-t-il un aspect que vous aimeriez explorer davantage ?",
)


def _last_user_text(messages: list[ChatMessage]) -> str:
    for entry in reversed(messages):
        if entry["role"] == "user":
            return entry["content"]
    return ""


def _system_prompt(messages: list[ChatMessage]) -> str:
    return messages[0]["content"] if messages and messages[0]["role"] == "system" else ""


def compose(messages: list[ChatMessage]) -> str:
    text = _last_user_text(messages)
    system = _system_prompt(messages)
    idx = sum(text.encode("utf-8")) % len(_OPENERS)
    parts = [_OPENERS[idx]]

    words = len(text.split())
    if words >= 12:
        parts.append("Ce que vous décrivez semble prendre de la place, et je prends le temps de le lire.")

    one_question_only = "une seule question ciblée" in system
    prefers_few_questions = "peu de questions" in system
    if not (one_question_only and words < 6) and not prefers_few_questions:
        parts.append(_QUESTIONS[idx])
    return " ".join(parts)


class LocalSupportiveResponder:
    name = "local"
    version = "local-supportive-dev-1"

    async def health_check(self) -> bool:
        return True

    async def stream(self, messages: list[ChatMessage], *, max_tokens: int) -> AsyncIterator[str]:
        reply = compose(messages)
        emitted = 0
        for token in reply.split(" "):
            if emitted >= max_tokens:
                break
            # yield control so the caller can observe / cancel between fragments
            await asyncio.sleep(0)
            yield token if emitted == 0 else " " + token
            emitted += 1
