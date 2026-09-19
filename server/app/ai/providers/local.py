"""Répondeur de soutien local, non génératif, streamé — Phase 4.

Concret derrière `StreamingLLMProvider`. Compose une réponse
ACKNOWLEDGE → (REFLECT) → une question, à partir de gabarits + du contexte.
Ce n'est PAS une IA conversationnelle et ne doit jamais être présenté comme
telle. Repli du ``HybridLocalProvider`` (ADR-015) lorsqu'aucun serveur
d'inférence ni GGUF n'est disponible. Toujours GREEN uniquement
(voir ``compose_reply``).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.ai.prompt import ChatMessage

_OPENERS = (
    "Je vous entends.",
    "Merci d'avoir posé cela ici.",
    "Ce que vous décrivez mérite qu'on s'y arrête.",
)
_QUESTIONS = (
    "Qu'est-ce qui, dans ce que vous venez de dire, vous touche le plus ?",
    "Comment cela se manifeste-t-il pour vous au quotidien ?",
    "Si vous deviez nommer ce qui pèse le plus en ce moment, par où commenceriez-vous ?",
)


def _last_user_text(messages: list[ChatMessage]) -> str:
    for entry in reversed(messages):
        if entry["role"] == "user":
            return entry["content"]
    return ""


def _system_prompt(messages: list[ChatMessage]) -> str:
    return messages[0]["content"] if messages and messages[0]["role"] == "system" else ""


_REFLECTIONS = {
    "warm": "Je reformule pour être sûr de vous suivre : cela semble prendre beaucoup de place.",
    "neutral": "Vous décrivez quelque chose d'important ; je le note tel quel.",
    "direct": "C'est clair. Restons sur ce point.",
}
_SUGGESTIONS = (
    "Si cela vous convient, nous pouvons aussi repérer un moment de la journée où c'est un peu moins lourd — seulement si vous le souhaitez.",
)


def compose(messages: list[ChatMessage]) -> str:
    """Non génératif : la variation reflète la personnalisation (ton, longueur,
    fréquence de questions, directivité) telle qu'elle a été tissée dans le
    message système par `build_messages`. Un vrai LLM nuancerait ; ici on
    produit une variation grossière mais réelle et déterministe."""
    text = _last_user_text(messages)
    system = _system_prompt(messages)
    corpus = "".join(m["content"] for m in messages if m["role"] == "user")
    idx = sum(corpus.encode("utf-8")) % len(_OPENERS)
    qidx = (idx + len(messages) + len(text.split())) % len(_QUESTIONS)
    words = len(text.split())

    tone = "direct" if "ton direct" in system else ("neutral" if "ton neutre" in system else "warm")
    prefers_short = "1 à 2 phrases" in system
    prefers_detailed = "un peu plus développées" in system
    prefers_few_questions = "peu de questions" in system
    one_question_only = "une seule question ciblée" in system
    is_directive = "proposer une piste concrète" in system

    parts = [_OPENERS[idx]]
    if not prefers_short and (words >= 12 or prefers_detailed):
        parts.append(_REFLECTIONS[tone])
    ask_question = not prefers_few_questions and not (one_question_only and words < 6)
    if ask_question:
        parts.append(_QUESTIONS[qidx])
    if is_directive and not prefers_short:
        parts.append(_SUGGESTIONS[0])
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
